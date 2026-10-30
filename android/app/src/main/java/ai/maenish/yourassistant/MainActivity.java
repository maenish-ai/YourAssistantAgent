package ai.maenish.yourassistant;

import android.app.Activity;
import com.google.zxing.integration.android.IntentIntegrator;
import com.google.zxing.integration.android.IntentResult;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Small native Android client for the user's own home-computer assistant. */
public final class MainActivity extends Activity {
    private static final int PICK_ZIP = 40;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final Set<String> usedApprovalTokens = new HashSet<>();
    private final List<Button> approvalButtons = new ArrayList<>();
    private SecureStore credentials;
    private ApiClient api;
    private EditText serverField, tokenField, composer;
    private TextView status;
    private Button connectButton, disconnectButton, sendButton, attachButton, newChatButton, desktopButton, filesButton, computerButton;
    private boolean desktopAllowed, filesAllowed, aiAllowed;
    private LinearLayout connectionFields, transcript;
    private ScrollView scroll;
    private boolean resumed, destroyed, connected, busy, polling;
    private int generation;
    private long cursor;
    private boolean allowReconnect;
    private final Runnable reconnect=()->{if(resumed&&!destroyed&&allowReconnect&&api==null&&!busy)connect();};
    private final Runnable poll = this::pollEvents;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        credentials = new SecureStore(this);
        buildViews();
        serverField.setText(credentials.url());
        try { tokenField.setText(credentials.token()); }
        catch (Exception e) {
            credentials.clear();
            status.setText("تعذر فتح رمز الاقتران المحفوظ. أدخله مجدداً من إعدادات الكمبيوتر.");
        }
        allowReconnect=credentials.autoConnect() && credentials.url().startsWith("relay+https://");
        connectionFields.setVisibility(View.GONE);
        updateButtons();
        if (!allowReconnect && savedInstanceState != null && savedInstanceState.getBoolean("was_connected", false)
                && !tokenField.getText().toString().isEmpty()) main.post(this::connect);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("was_connected", connected);
        super.onSaveInstanceState(state);
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void buildViews() {
        LinearLayout root=AppUi.root(this);
        AppUi.header(this,root,"Your Assistant","كمبيوترك معك • Android "+BuildConfig.VERSION_NAME,false);
        LinearLayout pairing=AppUi.card(this);
        pairing.addView(label("ربط هاتفك بكمبيوتر البيت",16));
        pairing.addView(button("مسح QR وإقران الكمبيوتر",()->{
            IntentIntegrator scanner=new IntentIntegrator(this);
            scanner.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
            scanner.setPrompt("افتح ربط الهاتف في برنامج Windows وامسح الرمز");
            scanner.setBeepEnabled(false);scanner.setOrientationLocked(false);scanner.initiateScan();
        }));
        LinearLayout actions=row();
        actions.addView(button("اتصال",()->{
            if(serverField.getText().toString().isEmpty())showPairingHelp();else connect();
        }),weighted());
        actions.addView(AppUi.button(this,"إعدادات الربط",()->connectionFields.setVisibility(connectionFields.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE),false),weighted());
        disconnectButton=AppUi.button(this,"قطع الاتصال",this::disconnect,false);actions.addView(disconnectButton,weighted());
        pairing.addView(actions,AppUi.space(this));
        connectionFields=new LinearLayout(this);connectionFields.setOrientation(LinearLayout.VERTICAL);
        serverField=field("عنوان HTTPS — إعداد متقدم",false);serverField.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        tokenField=field("مفتاح الاقتران — إعداد متقدم",true);tokenField.setSaveEnabled(false);tokenField.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        connectionFields.addView(serverField,AppUi.space(this));connectionFields.addView(tokenField,AppUi.space(this));
        connectButton=button("حفظ واتصال",this::connect);connectionFields.addView(connectButton,AppUi.space(this));
        connectionFields.addView(AppUi.button(this,"كيف أربط الجهازين؟",this::showPairingHelp,false));pairing.addView(connectionFields);
        root.addView(pairing,AppUi.space(this));
        status=label("غير مقترن • اعرض QR من برنامج Windows ثم امسحه هنا.",12);status.setTextColor(AppUi.GREEN);root.addView(status);
        LinearLayout tools=row();
        desktopButton=AppUi.button(this,"سطح المكتب",()->startActivity(new Intent(this,DesktopActivity.class)),false);
        filesButton=AppUi.button(this,"الملفات",()->startActivity(new Intent(this,FilesActivity.class)),false);
        computerButton=AppUi.button(this,"المساعد الذكي",()->{composer.setText("/computer ");composer.setSelection(composer.length());composer.requestFocus();},false);
        tools.addView(desktopButton,weighted());tools.addView(filesButton,weighted());tools.addView(computerButton,weighted());root.addView(tools,AppUi.space(this));
        scroll=new ScrollView(this);scroll.setFillViewport(true);transcript=new LinearLayout(this);transcript.setOrientation(LinearLayout.VERTICAL);scroll.addView(transcript);
        root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout tasks=row();newChatButton=AppUi.button(this,"محادثة جديدة",this::newChat,false);attachButton=AppUi.button(this,"إرفاق ZIP",this::chooseZip,false);
        tasks.addView(newChatButton,weighted());tasks.addView(attachButton,weighted());root.addView(tasks,AppUi.space(this));
        composer=AppUi.field(this,"اطلب من مساعدك…");composer.setMinLines(1);composer.setMaxLines(3);composer.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        root.addView(composer,AppUi.space(this));sendButton=button("إرسال الطلب",this::sendText);root.addView(sendButton,AppUi.space(this));
    }

    private void showPairingHelp(){
        new android.app.AlertDialog.Builder(this).setTitle("ربط Windows وAndroid")
            .setMessage("١. حدّث برنامج Windows وافتح ربط الهاتف.\n٢. استورد ملف إعداد الخادم مرة واحدة. إذا لم يُجهّز الخادم، لن يكون هناك رمز صالح بعد.\n٣. فعّل صلاحيات الشاشة والملفات التي تريدها، ثم اعرض QR وامسحه هنا.\n\nاتصال خارج البيت يحتاج خادماً منشوراً. الكمبيوتر يجب أن يبقى مستيقظاً وبرنامجه مفتوحاً. قطع الاتصال يوقف هذا الهاتف؛ تغيير المفتاح من الكمبيوتر يلغي الاقتران.")
            .setPositiveButton("فهمت",null).show();
    }

    private TextView label(String text,int size){TextView v=AppUi.label(this,text,size,false);v.setTextIsSelectable(true);return v;}
    private EditText field(String hint,boolean secret){EditText v=AppUi.field(this,hint);v.setSingleLine(true);v.setTextDirection(View.TEXT_DIRECTION_LTR);if(secret)v.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);return v;}
    private Button button(String text,Runnable action){return AppUi.button(this,text,action,true);}

    private LinearLayout row() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.HORIZONTAL);
        return view;
    }

    private LinearLayout.LayoutParams weighted() {
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);p.setMargins(dp(3),dp(2),dp(3),dp(2));return p;
    }

    private boolean current(int requestGeneration) { return !destroyed && generation == requestGeneration; }

    private void updateButtons() {
        sendButton.setEnabled(connected && !busy);
        attachButton.setEnabled(connected && !busy);
        newChatButton.setEnabled(connected && !busy);
        composer.setEnabled(connected && !busy);
        connectButton.setEnabled(!busy);
        disconnectButton.setEnabled(api != null || allowReconnect);
        desktopButton.setEnabled(connected && desktopAllowed);filesButton.setEnabled(connected && filesAllowed);computerButton.setEnabled(connected && aiAllowed);
    }

    private void connect() {
        final ApiClient client;
        final String url = serverField.getText().toString().trim();
        final String token = tokenField.getText().toString().trim();
        try { client = new ApiClient(url, token); }
        catch (ApiClient.ApiException e) { status.setText(e.getMessage()); return; }
        allowReconnect=url.startsWith("relay+https://");
        credentials.autoConnect(allowReconnect);
        disconnect(false);
        api = client;
        final int requestGeneration = ++generation;
        busy = true;
        status.setText("جاري الاتصال بالكمبيوتر…");
        updateButtons();
        network.execute(() -> {
            try {
                JSONObject response = client.events(0);
                JSONObject permissions=client.capabilities();
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    try { credentials.save(client.origin(),token); }
                    catch(Exception e){busy=false;connected=false;client.close();api=null;status.setText("تعذر حفظ الاقتران بأمان. أعد المحاولة.");updateButtons();return;}
                    connected = true;
                    desktopAllowed=permissions.optBoolean("desktop");filesAllowed=permissions.optBoolean("files");aiAllowed=permissions.optBoolean("computer_ai");
                    busy = false;
                    cursor = 0;
                    usedApprovalTokens.clear();
                    transcript.removeAllViews();
                    connectionFields.setVisibility(View.GONE);
                    applyEvents(response);
                    status.setText(desktopAllowed?"● متصل • الشاشة والملفات حسب صلاحيات الكمبيوتر":"● متصل • فعّل التحكم من ربط الهاتف في Windows لإتاحة الشاشة والملفات");
                    updateButtons();
                    schedulePoll();
                });
            } catch (Exception e) {
                String error = e instanceof ApiClient.ApiException ? e.getMessage() : "تعذر حفظ إعدادات الاتصال بأمان.";
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    busy = false;
                    connected = false;
                    client.close();
                    api = null;
                    status.setText(error);
                    updateButtons();
                    scheduleReconnect();
                });
            }
        });
    }

    private void scheduleReconnect(){
        main.removeCallbacks(reconnect);
        if(allowReconnect&&resumed&&!destroyed&&api==null)main.postDelayed(reconnect,5000);
    }

    private void disconnect() { disconnect(true); }
    private void disconnect(boolean userRequested) {
        if(userRequested){allowReconnect=false;credentials.autoConnect(false);}
        main.removeCallbacks(reconnect);
        ++generation;
        connected = false;
        busy = false;
        polling = false;
        main.removeCallbacks(poll);
        if (api != null) api.close();
        api = null;
        disableApprovals();
        if (status != null) status.setText("غير متصل. المهام التي وصلت للكمبيوتر قد تستمر؛ راجع حالتها عند إعادة الاتصال.");
        updateButtons();
    }

    private void schedulePoll() {
        main.removeCallbacks(poll);
        if (resumed && connected && !destroyed) main.postDelayed(poll, 2000);
    }

    private void pollEvents() {
        if (!resumed || !connected || destroyed || polling || api == null) return;
        polling = true;
        ApiClient client = api;
        int requestGeneration = generation;
        long after = cursor;
        network.execute(() -> {
            try {
                JSONObject response = client.events(after);
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    polling = false;
                    applyEvents(response);
                    status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
                    schedulePoll();
                });
            } catch (ApiClient.ApiException e) {
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    polling = false;
                    if (e.status == 401 || e.status == 403) {
                        disconnect(!allowReconnect);
                        if(!allowReconnect)connectionFields.setVisibility(View.VISIBLE);
                        scheduleReconnect();
                    }
                    status.setText(e.getMessage());
                    schedulePoll();
                });
            }
        });
    }

    private void applyEvents(JSONObject response) {
        if (response.optBoolean("reset", false)) {
            cursor = 0;
            transcript.removeAllViews();
            disableApprovals();
            usedApprovalTokens.clear();
        }
        JSONArray events = response.optJSONArray("events");
        if (events != null) for (int i = 0; i < events.length(); i++) {
            JSONObject event = events.optJSONObject(i);
            if (event == null) continue;
            long id = event.optLong("id", 0);
            if (id <= cursor) continue;
            if (event.optBoolean("clear_approval", false)) disableApprovals();
            String text = event.optString("text", "");
            if ("approval".equals(event.optString("type"))) showApproval(event, text);
            else appendText(text, "المساعد");
            if (event.has("download_path")) {
                Button download = button("حفظ الملف على الهاتف", () -> {
                    if (connected) startActivity(new Intent(this, FilesActivity.class)
                            .putExtra("download_path", event.optString("download_path"))
                            .putExtra("download_name", event.optString("download_name", "download")));
                });
                transcript.addView(download); trimAndScroll();
            }
            cursor = id;
        }
        cursor = Math.max(cursor, response.optLong("cursor", cursor));
    }

    private void appendText(String text, String sender) {
        if (text.isEmpty()) return;
        TextView view = label(sender + "\n" + text, 16);
        view.setBackground(AppUi.shape("أنت".equals(sender)?Color.rgb(47,40,83):AppUi.PANEL,dp(16)));
        view.setPadding(dp(14),dp(12),dp(14),dp(12));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, dp(5), 0, dp(5));
        transcript.addView(view, params);
        trimAndScroll();
    }

    private void trimAndScroll() {
        while (transcript.getChildCount() > 160) transcript.removeViewAt(0);
        scroll.post(() -> scroll.fullScroll(View.FOCUS_DOWN));
    }

    private void disableApprovals() {
        for (Button button : approvalButtons) button.setEnabled(false);
        approvalButtons.clear();
    }

    private void showApproval(JSONObject event, String text) {
        disableApprovals();
        String token = event.optString("token", "");
        long expires = (long) (event.optDouble("expires_at", 0) * 1000);
        appendText(text, "معاينة قبل التنفيذ");
        if (token.isEmpty() || usedApprovalTokens.contains(token)) return;
        if (expires > 0) appendText("صلاحية الموافقة حتى " + DateFormat.getTimeInstance(DateFormat.SHORT).format(new Date(expires)), "الموافقة");
        LinearLayout actions = row();
        Button approve = button("موافق — نفّذ", () -> submitApproval(token, true, expires));
        Button cancel = button("إلغاء", () -> submitApproval(token, false, expires));
        boolean fresh = expires == 0 || System.currentTimeMillis() < expires;
        approve.setEnabled(fresh);
        cancel.setEnabled(fresh);
        approvalButtons.add(approve);
        approvalButtons.add(cancel);
        actions.addView(approve, weighted());
        actions.addView(cancel, weighted());
        transcript.addView(actions);
        trimAndScroll();
    }

    private void submitApproval(String token, boolean approve, long expires) {
        if (!connected || busy || usedApprovalTokens.contains(token)) return;
        if (expires > 0 && System.currentTimeMillis() >= expires) {
            disableApprovals();
            status.setText("انتهت صلاحية المعاينة. اطلب تجهيز العملية مجدداً.");
            return;
        }
        usedApprovalTokens.add(token);
        disableApprovals();
        try {
            JSONObject body = new JSONObject().put("token", token).put("approve", approve);
            submit("/v1/approvals", body, approve ? "أرسلت موافقتك؛ انتظر نتيجة التنفيذ." : "أرسلت طلب الإلغاء.", null);
        } catch (Exception e) { status.setText("تعذر تجهيز الموافقة."); }
    }

    private void sendText() {
        String text = composer.getText().toString().trim();
        if (!connected || busy || text.isEmpty()) return;
        if (text.length() > 5000) { status.setText("اختصر الرسالة إلى 5000 حرف أو أقل."); return; }
        try {
            JSONObject body = new JSONObject().put("text", text);
            submit("/v1/messages", body, "وصل الطلب لقائمة المهام؛ النتيجة تظهر في المحادثة.", () -> {
                appendText(text, "أنت");
                composer.setText("");
            });
        } catch (Exception e) { status.setText("تعذر تجهيز الرسالة."); }
    }

    private void newChat() {
        if (!connected || busy) return;
        submit("/v1/new-chat", new JSONObject(), "طلبت محادثة جديدة.", () -> {
            disableApprovals();
            transcript.removeAllViews();
        });
    }

    private void submit(String path, JSONObject body, String success, Runnable accepted) {
        ApiClient client = api;
        if (client == null || busy) return;
        int requestGeneration = generation;
        disableApprovals();
        busy = true;
        status.setText("جاري إرسال الطلب…");
        updateButtons();
        network.execute(() -> {
            try {
                client.post(path, body);
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    busy = false;
                    if (accepted != null) accepted.run();
                    status.setText(success);
                    updateButtons();
                    schedulePoll();
                });
            } catch (ApiClient.ApiException e) {
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    busy = false;
                    status.setText(e.getMessage());
                    updateButtons();
                    schedulePoll();
                });
            }
        });
    }

    private void chooseZip() {
        if (!connected || busy) return;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.setType("*/*");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/zip", "application/x-zip-compressed", "application/octet-stream"});
        startActivityForResult(intent, PICK_ZIP);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        IntentResult scanned=IntentIntegrator.parseActivityResult(requestCode,resultCode,data);
        if(scanned!=null){
            if(scanned.getContents()!=null)importPairing(scanned.getContents());
            return;
        }
        if (requestCode != PICK_ZIP || resultCode != RESULT_OK || data == null || data.getData() == null || !connected || busy) return;
        Uri uri = data.getData();
        String name = "";
        long size = -1;
        try (Cursor metadata = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE}, null, null, null)) {
            if (metadata != null && metadata.moveToFirst()) {
                name = metadata.getString(0);
                if (!metadata.isNull(1)) size = metadata.getLong(1);
            }
        } catch (Exception e) { status.setText("تعذر قراءة معلومات الملف."); return; }
        if (name == null || !name.toLowerCase(Locale.ROOT).endsWith(".zip") || size > ApiClient.MAX_UPLOAD_BYTES || size == 0) {
            status.setText("اختر ملف ZIP لا يتجاوز 20 MiB.");
            return;
        }
        upload(uri);
    }

    private void importPairing(String raw){
        try{
            if(raw.length()>2048)throw new Exception();
            JSONObject code=new JSONObject(raw);
            if(!"yaa-relay".equals(code.optString("type"))||code.optInt("v")!=1)throw new Exception();
            String address="relay+"+code.getString("url"),secret=code.getString("token");
            ApiClient validation=new ApiClient(address,secret);validation.close();
            credentials.save(address,secret);credentials.autoConnect(true);
            serverField.setText(address);tokenField.setText(secret);allowReconnect=true;
            connect();
        }catch(Exception e){status.setText("هذا ليس رمز إقران صالحاً. امسح الرمز من برنامج الكمبيوتر الجديد.");}
    }

    private void upload(Uri uri) {
        ApiClient client = api;
        if (client == null) return;
        int requestGeneration = generation;
        disableApprovals();
        busy = true;
        status.setText("جاري إرسال ZIP للكمبيوتر؛ لن تُرفع تعديلاته إلى GitHub قبل المعاينة والموافقة.");
        updateButtons();
        network.execute(() -> {
            File temporary = null;
            try {
                temporary = File.createTempFile("upload-", ".zip", getCacheDir());
                long received = 0;
                try (InputStream input = getContentResolver().openInputStream(uri);
                     FileOutputStream output = new FileOutputStream(temporary)) {
                    if (input == null) throw new ApiClient.ApiException("تعذر فتح الملف المحدد.");
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = input.read(buffer)) != -1) {
                        received += count;
                        if (received > ApiClient.MAX_UPLOAD_BYTES) throw new ApiClient.ApiException("الملف يتجاوز 20 MiB.");
                        output.write(buffer, 0, count);
                    }
                }
                client.progress((done,total)->main.post(()->{if(current(requestGeneration))status.setText("إرسال ZIP • "+AppUi.size(done)+" / "+AppUi.size(total));}));
                client.upload(temporary);
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    busy = false;
                    status.setText("وصل الملف للكمبيوتر. انتظر المعاينة قبل الموافقة على رفع التعديلات.");
                    updateButtons();
                    schedulePoll();
                });
            } catch (Exception e) {
                String error = e instanceof ApiClient.ApiException ? e.getMessage() : "تعذر قراءة أو إرسال ZIP. افحص المحادثة قبل إعادة المحاولة.";
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    busy = false;
                    status.setText(error);
                    updateButtons();
                    schedulePoll();
                });
            } finally { if (temporary != null) temporary.delete(); }
        });
    }

    @Override protected void onResume() {
        super.onResume();
        resumed = true;
        if(allowReconnect&&api==null&&!busy)connect();
        else schedulePoll();
    }

    @Override protected void onPause() {
        resumed = false;
        main.removeCallbacks(reconnect);
        main.removeCallbacks(poll);
        super.onPause();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        ++generation;
        main.removeCallbacksAndMessages(null);
        if (api != null) api.close();
        network.shutdownNow();
        super.onDestroy();
    }
}
