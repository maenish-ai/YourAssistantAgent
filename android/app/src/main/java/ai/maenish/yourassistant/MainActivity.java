package ai.maenish.yourassistant;

import android.app.Activity;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.speech.tts.UtteranceProgressListener;
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
    private static final int RECORD_PERMISSION=41;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final Set<String> usedApprovalTokens = new HashSet<>();
    private final List<Button> approvalButtons = new ArrayList<>();
    private SecureStore credentials;
    private ApiClient api;
    private EditText serverField, tokenField, composer;
    private TextView status;
    private Button connectButton, disconnectButton, diagnosticsButton, sendButton, attachButton, newChatButton, desktopButton, filesButton, computerButton;
    private boolean desktopAllowed, filesAllowed, aiAllowed;
    private boolean dictationAllowed;
    private boolean recordAfterPermission;
    private Button micButton, callButton;
    private TextToSpeech voice;
    private BundledFemaleVoice bundledVoice;
    private String activeTtsEngine="";
    private boolean ttsInitializing=false;
    private boolean callMode=false, waitingForReply=false, speaking=false;
    private long lastSpeechMs=0, listeningSinceMs=0;
    private final Runnable silenceDetector=new Runnable(){
        @Override public void run(){
            if(!callMode||dictation==null||!dictation.active())return;
            long now=android.os.SystemClock.elapsedRealtime();
            int level=dictation.amplitude();
            if(level>900)lastSpeechMs=now;
            if(now-listeningSinceMs>1800 && lastSpeechMs>0 && now-lastSpeechMs>1250){dictation.finish();return;}
            if(now-listeningSinceMs>12000){dictation.finish();return;}
            main.postDelayed(this,150);
        }
    };
    private PhoneDictation dictation;
    private String pendingDictationId;
    private final Runnable dictationTimeout=()->{if(pendingDictationId!=null){pendingDictationId=null;status.setText("تأخر تفريغ الصوت. لم يُرسل أي أمر؛ يمكنك إعادة التسجيل.");if(callMode)main.postDelayed(this::startCallListening,600);updateButtons();}};
    private LinearLayout connectionFields, transcript;
    private ScrollView scroll;
    private boolean resumed, destroyed, connected, busy, polling;
    private int generation;
    private long cursor;
    private boolean allowReconnect;
    private boolean voiceRequested;
    private boolean safeMode;
    private CrashDiagnostics crashDiagnostics;
    private final Runnable reconnect=()->{if(resumed&&!destroyed&&allowReconnect&&api==null&&!busy)connect();};
    private final Runnable poll = this::pollEvents;

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        crashDiagnostics = new CrashDiagnostics(this);
        crashDiagnostics.begin();
        safeMode = crashDiagnostics.safeMode();
        crashDiagnostics.stage("secure_store");
        credentials = new SecureStore(this);
        crashDiagnostics.stage("build_views");
        buildViews();
        // Native offline voice is deliberately lazy: do not load ONNX during app startup.
        crashDiagnostics.stage("create_dictation");
        dictation=new PhoneDictation(this,new PhoneDictation.Listener(){
            public void recording(boolean active){micButton.setText(active?"إنهاء التسجيل":"🎙 إملاء صوتي");if(active)status.setText(callMode?"مكالمة مباشرة • تحدث الآن، وسأتوقف عند نهاية كلامك":"أسجل صوتك… اضغط إنهاء التسجيل؛ النص يرجع للمراجعة قبل الإرسال.");updateButtons();}
            public void ready(File audio){uploadDictation(audio);}
            public void error(String message){status.setText(message);updateButtons();}
        });
        if(savedInstanceState!=null)pendingDictationId=savedInstanceState.getString("dictation_id");
        if(pendingDictationId!=null)main.postDelayed(dictationTimeout,90000);
        serverField.setText(credentials.url());
        try { tokenField.setText(credentials.token()); }
        catch (Exception e) {
            credentials.clear();
            status.setText("تعذر فتح رمز الاقتران المحفوظ. أدخله مجدداً من إعدادات الكمبيوتر.");
        }
        allowReconnect=!safeMode && credentials.autoConnect() && ApiClient.automaticOrigin(credentials.url());
        connectionFields.setVisibility(View.GONE);
        updateButtons();
        crashDiagnostics.stage("startup_complete");
        main.postDelayed(() -> { if (!destroyed && resumed) crashDiagnostics.healthy(); }, 15000);
        // Do not auto-connect on activity recreation; the user can connect manually.
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("was_connected", connected);
        state.putString("dictation_id",pendingDictationId);
        super.onSaveInstanceState(state);
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void buildViews() {
        LinearLayout root=AppUi.root(this);
        AppUi.header(this,root,"Your Assistant","كمبيوترك معك • Android "+BuildConfig.VERSION_NAME,false);
        LinearLayout pairing=AppUi.card(this);
        pairing.addView(label("ربط هاتفك بكمبيوتر البيت",16));
        pairing.addView(button("مسح QR وإقران الكمبيوتر",this::scanPairing));
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
        diagnosticsButton=AppUi.button(this,"تشخيص الاتصال",this::diagnostics,false);connectionFields.addView(diagnosticsButton,AppUi.space(this));
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
        root.addView(composer,AppUi.space(this));
        micButton=AppUi.button(this,"🎙 إملاء صوتي",this::toggleDictation,false);
        callButton=AppUi.button(this,"☎ بدء محادثة صوتية",this::toggleCall,false);
        root.addView(callButton,AppUi.space(this));
        root.addView(AppUi.button(this,"تقرير أعطال التطبيق",this::showCrashReport,false),AppUi.space(this));
        root.addView(AppUi.button(this,"🔊 اختيار صوت موظفة طبيعي من الهاتف",
            this::openVoiceSettings,false),AppUi.space(this));
        root.addView(AppUi.label(this,"المحادثة الذكية تستخدم Groq؛ التحكم اليدوي والملفات لهما أزرار منفصلة.",11,true));
        sendButton=button("إرسال الطلب",this::sendText);LinearLayout sendRow=row();sendRow.addView(micButton,weighted());sendRow.addView(sendButton,weighted());root.addView(sendRow,AppUi.space(this));
    }

    private void showCrashReport(){
        new android.app.AlertDialog.Builder(this).setTitle("تشخيص أعطال Android")
            .setMessage(crashDiagnostics.report())
            .setPositiveButton("نسخ التقرير",(d,w)->{
                android.content.ClipboardManager cb=(android.content.ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
                if(cb!=null)cb.setPrimaryClip(android.content.ClipData.newPlainText("Android diagnostics",crashDiagnostics.report()));
            })
            .setNeutralButton("تشغيل عادي في المرة القادمة",(d,w)->crashDiagnostics.clearSafeMode())
            .setNegativeButton("إغلاق",null).show();
    }

    private void ensureVoice(){
        if(voiceRequested || safeMode) return;
        voiceRequested=true;
        crashDiagnostics.stage("voice_user_requested");
        try {
            bundledVoice=new BundledFemaleVoice(this,main,new BundledFemaleVoice.Listener(){
                public void onStart(){speaking=true;}
                public void onDone(){speaking=false;if(callMode&&!waitingForReply)startCallListening();}
                public void onError(String reason){if(status!=null)status.setText("تعذر تشغيل الصوت المحلي؛ سيتم استخدام صوت الهاتف.");}
            });
            // Do not eagerly load the native ONNX model: system TTS is the stable fallback.
            initializeVoiceEngine();
        }catch(Throwable t){crashDiagnostics.failure("voice_setup",t);voiceRequested=false;}
    }

    private void scanPairing(){
        try{
            IntentIntegrator scanner=new IntentIntegrator(this);
            scanner.setCaptureActivity(PairingCaptureActivity.class);
            scanner.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE);
            scanner.setPrompt("افتح ربط الهاتف في برنامج Windows وامسح الرمز");
            scanner.addExtra("SHOW_MISSING_CAMERA_PERMISSION_DIALOG",true);
            scanner.addExtra("MISSING_CAMERA_PERMISSION_DIALOG_MESSAGE","اسمح بالكاميرا لمسح رمز الكمبيوتر. يمكنك تفعيل الإذن من إعدادات التطبيق ثم المحاولة مجدداً.");
            scanner.setBeepEnabled(false);scanner.setOrientationLocked(false);scanner.initiateScan();
        }catch(RuntimeException e){
            status.setText("تعذر فتح ماسح QR. تأكد من إتاحة الكاميرا للتطبيق ثم أعد المحاولة.");
        }
    }

    private void showPairingHelp(){
        new android.app.AlertDialog.Builder(this).setTitle("ربط Windows وAndroid")
            .setMessage("١. افتح ربط الهاتف في برنامج Windows واختر الاستضافة على هذا الكمبيوتر.\n٢. فعّل الاتصال والصلاحيات ثم امسح QR داخل شبكة البيت أول مرة.\n٣. للوصول من خارج البيت أضف عنوان HTTPS العام وافتح منفذ البرنامج في راوتر البيت. إذا كان الاتصال خلف CGNAT ولا يوجد IPv6 متاح، لا يمكن الوصول المباشر من الخارج.\n\nالكمبيوتر يستضيف الاتصال بنفسه ويجب أن يبقى مستيقظاً وبرنامجه مفتوحاً. قطع الاتصال يوقف هذا الهاتف؛ تغيير المفتاح من الكمبيوتر يلغي الاقتران.")
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
        boolean voiceActive=dictation!=null&&dictation.active();
        boolean voiceWaiting=pendingDictationId!=null;
        sendButton.setEnabled(connected && !busy&&!voiceActive&&!voiceWaiting);
        attachButton.setEnabled(connected && !busy&&!voiceActive&&!voiceWaiting);
        newChatButton.setEnabled(connected && !busy&&!voiceActive&&!voiceWaiting);
        diagnosticsButton.setEnabled(connected && !busy&&!voiceActive&&!voiceWaiting);
        micButton.setEnabled(!callMode&&(voiceActive||(connected&&dictationAllowed&&!busy&&!voiceWaiting)));
        if(callButton!=null){callButton.setEnabled(callMode||(connected&&dictationAllowed));callButton.setText(callMode?"■ إنهاء المكالمة":"☎ بدء محادثة صوتية");}
        composer.setEnabled(connected && !busy);
        connectButton.setEnabled(!busy);
        disconnectButton.setEnabled(api != null || allowReconnect);
        desktopButton.setEnabled(connected && desktopAllowed);filesButton.setEnabled(connected && filesAllowed);computerButton.setEnabled(connected && aiAllowed);
    }

    private void connect() {
        crashDiagnostics.stage("connecting");
        final ApiClient client;
        final String url = serverField.getText().toString().trim();
        final String token = tokenField.getText().toString().trim();
        try { client = new ApiClient(url, token); }
        catch (ApiClient.ApiException e) { status.setText(e.getMessage()); return; }
        allowReconnect=ApiClient.automaticOrigin(url);
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
                    crashDiagnostics.stage("connected");
                    connected = true;
                    desktopAllowed=permissions.optBoolean("desktop");filesAllowed=permissions.optBoolean("files");aiAllowed=permissions.optBoolean("computer_ai");
                    dictationAllowed=permissions.optBoolean("dictation");
                    busy = false;
                    cursor = 0;
                    usedApprovalTokens.clear();
                    transcript.removeAllViews();
                    connectionFields.setVisibility(View.GONE);
                    applyEvents(response);
                    status.setText(desktopAllowed?"● متصل بـ "+permissions.optString("computer_name","الكمبيوتر")+" • Windows "+permissions.optString("version","")+(dictationAllowed?" • الإملاء متاح":" • حدّث Windows إلى 5.0 للإملاء"):
                        "● متصل • اضغط تفعيل التحكم الكامل وعرض QR في برنامج Windows لإتاحة الشاشة والملفات والمساعد");
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
        if(allowReconnect&&resumed&&!destroyed&&api==null)main.postDelayed(reconnect,15000);
    }

    private void disconnect() { disconnect(true); }
    private void disconnect(boolean userRequested) {
        endCall();
        if(dictation!=null)dictation.cancel();
        if(userRequested){pendingDictationId=null;recordAfterPermission=false;main.removeCallbacks(dictationTimeout);}
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
                    CharSequence before=status.getText();applyEvents(response);
                    if(android.text.TextUtils.equals(before,status.getText()))status.setText("متصل • التحديث تلقائي أثناء فتح التطبيق.");
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
            if("progress".equals(event.optString("type"))) {
                JSONObject progress = event.optJSONObject("progress");
                String state = progress == null ? "working" : progress.optString("state", "working");
                String label = "done".equals(state) ? "✓ اكتملت المهمة" :
                        "failed".equals(state) ? "⚠ تعذرت المهمة" :
                        "stopped".equals(state) ? "■ توقفت المهمة" :
                        "started".equals(state) ? "▶ بدأت المهمة" : "◷ جاري التنفيذ";
                appendText(label + "\n" + text, "تقدم المهمة");
            }
            else if("dictation".equals(event.optString("type")))applyDictation(event);
            else if ("approval".equals(event.optString("type"))) {showApproval(event, text);if(callMode){waitingForReply=true;say("هناك طلب موافقة على الشاشة. راجعه واضغط موافق أو إلغاء.");}}
            else {appendText(text, "المساعد");if(callMode && !text.isEmpty() && !"progress".equals(event.optString("type"))){waitingForReply=false;say(text);}}
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
        if((dictation!=null&&dictation.active())||pendingDictationId!=null)return;
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
        if((dictation!=null&&dictation.active())||pendingDictationId!=null)return;
        if (!connected || busy) return;
        submit("/v1/new-chat", new JSONObject(), "طلبت محادثة جديدة.", () -> {
            disableApprovals();
            transcript.removeAllViews();
        });
    }

    private void diagnostics() {
        if (!connected || busy || (dictation!=null&&dictation.active()) || pendingDictationId!=null) return;
        try {
            JSONObject body=new JSONObject().put("text","/diagnostics");
            submit("/v1/messages",body,"طلبت تقرير التشخيص من الكمبيوتر؛ يظهر هنا بدون استخدام Groq.",()->{
                appendText("تشخيص الاتصال","أنت");
                connectionFields.setVisibility(View.GONE);
            },false);
        } catch(Exception e) { status.setText("تعذر تجهيز طلب التشخيص."); }
    }

    private void submit(String path, JSONObject body, String success, Runnable accepted) {
        submit(path,body,success,accepted,true);
    }

    private void submit(String path, JSONObject body, String success, Runnable accepted, boolean invalidateApproval) {
        ApiClient client = api;
        if (client == null || busy) return;
        int requestGeneration = generation;
        if(invalidateApproval)disableApprovals();
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
            else if(data!=null&&data.getBooleanExtra("MISSING_CAMERA_PERMISSION",false))status.setText("لم يُسمح بالكاميرا. فعّل إذن الكاميرا لهذا التطبيق ثم اضغط مسح QR مجدداً.");
            else status.setText(connected?"متصل • أُلغي مسح QR وبقي الاتصال الحالي.":"أُلغي مسح QR. يمكنك المحاولة مجدداً من زر المسح.");
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
            if(code.optInt("v")!=1)throw new Exception();
            String address,secret=code.getString("token");
            if("yaa-direct".equals(code.optString("type")))address=new HomeProfile(code).encode();
            else if("yaa-relay".equals(code.optString("type")))address="relay+"+code.getString("url");
            else throw new Exception();
            ApiClient validation=new ApiClient(address,secret);validation.close();
            pendingDictationId=null;main.removeCallbacks(dictationTimeout);
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

    // Prefer a locally installed high-quality Arabic voice. This does not install
    // a new voice engine or guarantee a Jordanian accent.
    // Uses the phone's installed neural TTS engine (e.g. HayaiTTS) when
    // selected in Android's system settings. No API key or cloud TTS required.
    private void initializeVoiceEngine(){
        if(ttsInitializing)return;
        ttsInitializing=true;
        if(voice!=null){voice.stop();voice.shutdown();voice=null;}
        voice=new TextToSpeech(this, result->main.post(()->{
            ttsInitializing=false;
            if(destroyed)return;
            if(result!=TextToSpeech.SUCCESS){
                status.setText("تعذر تشغيل محرك الصوت. تحقق من إعدادات تحويل النص إلى كلام.");
                if(callMode)endCall();
                voiceRequested=false;
                return;
            }
            activeTtsEngine=voice.getDefaultEngine();
            configureArabicVoice();
            voice.setOnUtteranceProgressListener(new UtteranceProgressListener(){
                @Override public void onStart(String id){main.post(()->speaking=true);}
                @Override public void onDone(String id){main.post(()->{
                    speaking=false;if(callMode&&!waitingForReply)startCallListening();
                });}
                @Override public void onError(String id){main.post(()->{
                    speaking=false;if(callMode&&!waitingForReply)startCallListening();
                });}
            });
            if(callMode) say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");
        }));
    }

    private void openVoiceSettings(){
        if(callMode)endCall();
        try {
            startActivity(new Intent("com.android.settings.TTS_SETTINGS"));
        }catch(Exception e){
            status.setText("افتح إعدادات الهاتف ← تحويل النص إلى كلام، واختر محرك الصوت العصبي.");
        }
    }

    private void configureArabicVoice(){
        if(voice==null)return;
        Locale preferred=new Locale("ar","JO");
        int available=voice.setLanguage(preferred);
        if(available==TextToSpeech.LANG_MISSING_DATA || available==TextToSpeech.LANG_NOT_SUPPORTED)
            voice.setLanguage(new Locale("ar"));
        Voice best=null;
        int bestScore=Integer.MIN_VALUE;
        try {
            java.util.Set<Voice> voices=voice.getVoices();
            if(voices!=null)for(Voice candidate:voices){
                Locale locale=candidate.getLocale();
                if(locale==null || !"ar".equals(locale.getLanguage()))continue;
                int score=0;
                if("JO".equalsIgnoreCase(locale.getCountry()))score+=100;
                else if("SA".equalsIgnoreCase(locale.getCountry()))score+=20;
                if(!candidate.isNetworkConnectionRequired())score+=10;
                score+=candidate.getQuality()/10; // higher quality values are better
                if(score>bestScore){best=candidate;bestScore=score;}
            }
            if(best!=null)voice.setVoice(best);
        } catch(Exception ignored) { /* Retain engine default if voice discovery fails. */ }
        voice.setSpeechRate(0.96f);
        voice.setPitch(1.0f);
    }

    private void toggleCall(){
        if(callMode){endCall();status.setText("انتهت المكالمة. يمكنك متابعة الكتابة.");return;}
        if(!connected||!dictationAllowed)return;
        ensureVoice();
        callMode=true;waitingForReply=false;updateButtons();
        if(safeMode || (!ttsInitializing && voice==null)){
            endCall();status.setText("تعذر تشغيل الصوت. راجع إعدادات محرك تحويل النص إلى كلام.");return;
        }
        if(!ttsInitializing)say("أهلاً، أنا جاهزة. احكي لي شو بدك أعمل على الكمبيوتر.");
    }
    private void say(String message){
        if(!callMode||voice==null)return;
        if(dictation!=null&&dictation.active())dictation.cancel();
        main.removeCallbacks(silenceDetector);
        speaking=true;
        String clean=message.replaceAll("https?://\\S+","رابط");
        if(clean.length()>1200)clean=clean.substring(0,1200);
        if(bundledVoice!=null && bundledVoice.ready()){
            bundledVoice.speak(clean);
            return;
        }
        int result=voice.speak(clean,TextToSpeech.QUEUE_FLUSH,null,"reply-"+System.nanoTime());
        if(result==TextToSpeech.ERROR){speaking=false;if(!waitingForReply)startCallListening();}
    }
    private void startCallListening(){
        if(!callMode||!resumed||!connected||busy||speaking||waitingForReply||pendingDictationId!=null)return;
        if(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED){
            requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO},RECORD_PERMISSION);return;
        }
        dictation.start();listeningSinceMs=android.os.SystemClock.elapsedRealtime();lastSpeechMs=0;
        main.removeCallbacks(silenceDetector);main.postDelayed(silenceDetector,200);
    }
    private void endCall(){
        callMode=false;waitingForReply=false;speaking=false;
        main.removeCallbacks(silenceDetector);
        if(bundledVoice!=null)bundledVoice.stop();
        if(voice!=null)voice.stop();
        if(dictation!=null&&dictation.active())dictation.cancel();
        if(callButton!=null)updateButtons();
    }
    private void toggleDictation(){
        if(dictation.active()){dictation.finish();return;}
        if(!connected||!dictationAllowed||busy||pendingDictationId!=null)return;
        if(checkSelfPermission(android.Manifest.permission.RECORD_AUDIO)!=android.content.pm.PackageManager.PERMISSION_GRANTED){
            requestPermissions(new String[]{android.Manifest.permission.RECORD_AUDIO},RECORD_PERMISSION);return;
        }
        dictation.start();
    }

    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] results){
        super.onRequestPermissionsResult(code,permissions,results);
        if(code!=RECORD_PERMISSION)return;
        if(results.length>0&&results[0]==android.content.pm.PackageManager.PERMISSION_GRANTED){
            recordAfterPermission=true;
            if(resumed&&connected&&!busy&&pendingDictationId==null){recordAfterPermission=false;if(callMode)startCallListening();else dictation.start();}
        }else status.setText("لم يُسمح بالميكروفون. فعّل إذن التسجيل من إعدادات التطبيق؛ يمكنك الاستمرار بالكتابة.");
    }

    private void uploadDictation(File audio){
        ApiClient client=api;
        if(client==null||!connected||destroyed){audio.delete();return;}
        String id=java.util.UUID.randomUUID().toString();pendingDictationId=id;
        int requestGeneration=generation;busy=true;status.setText("أرسل الصوت للكمبيوتر لتفريغه…");updateButtons();
        main.removeCallbacks(dictationTimeout);main.postDelayed(dictationTimeout,90000);
        network.execute(()->{
            try{
                client.dictation(audio,id);
                main.post(()->{if(!current(requestGeneration))return;busy=false;status.setText(callMode?"أحلل كلامك عبر Groq…":"وصل التسجيل. أنتظر النص من Groq؛ لن يُرسل كطلب تلقائياً.");updateButtons();schedulePoll();});
            }catch(Exception e){
                main.post(()->{if(!current(requestGeneration))return;busy=false;pendingDictationId=null;main.removeCallbacks(dictationTimeout);status.setText(e instanceof ApiClient.ApiException?e.getMessage():"تعذر إرسال التسجيل؛ لم يُرسل أمر للمساعد.");updateButtons();});
            }finally{audio.delete();}
        });
    }

    private void applyDictation(JSONObject event){
        if(pendingDictationId==null||!pendingDictationId.equals(event.optString("dictation_id")))return;
        pendingDictationId=null;main.removeCallbacks(dictationTimeout);
        String text=event.optString("dictation_text","").trim();
        if(!text.isEmpty()){
            if(callMode){
                appendText(text,"أنت");waitingForReply=true;
                try{submit("/v1/messages",new JSONObject().put("text",text),"تم إرسال كلامك إلى Groq؛ أنتظر الرد.",null);}catch(Exception e){waitingForReply=false;status.setText("تعذر إرسال الأمر الصوتي.");}
            }else{
                String before=composer.getText().toString();composer.append((before.isEmpty()||Character.isWhitespace(before.charAt(before.length()-1))?"":" ")+text);
                composer.setSelection(composer.length());status.setText("راجع النص وعدّله ثم اضغط إرسال. لم يُنفّذ أي أمر صوتي تلقائياً.");
            }
        }else {status.setText(event.optString("dictation_error","لم يصل كلام واضح. أعد التسجيل."));if(callMode)main.postDelayed(this::startCallListening,600);}
        updateButtons();
    }

    @Override protected void onResume() {
        super.onResume();
        if(voiceRequested && voice!=null && !ttsInitializing){
            String engine=android.provider.Settings.Secure.getString(
                getContentResolver(),"tts_default_synth");
            if(engine!=null && !engine.equals(activeTtsEngine))initializeVoiceEngine();
        }

        resumed = true;
        if(pendingDictationId!=null){main.removeCallbacks(dictationTimeout);main.postDelayed(dictationTimeout,90000);}
        if(recordAfterPermission&&connected&&!busy&&pendingDictationId==null){recordAfterPermission=false;dictation.start();}
        if(allowReconnect&&api==null&&!busy){
            crashDiagnostics.stage("auto_connect_scheduled");
            main.removeCallbacks(reconnect);
            main.postDelayed(reconnect, 12000);
        }
        else schedulePoll();
    }

    @Override protected void onPause() {
        main.removeCallbacks(dictationTimeout);
        if(callMode)endCall();
        if(dictation!=null&&dictation.active()){dictation.cancel();status.setText("أُلغي التسجيل لأن التطبيق انتقل للخلفية؛ لم يُرسل الصوت.");}
        resumed = false;
        main.removeCallbacks(reconnect);
        main.removeCallbacks(poll);
        if (crashDiagnostics != null) crashDiagnostics.suspended();
        super.onPause();
    }

    @Override protected void onDestroy() {
        destroyed = true;
        if(dictation!=null)dictation.cancel();
        if(bundledVoice!=null)bundledVoice.close();
        if(voice!=null){voice.stop();voice.shutdown();}
        ++generation;
        main.removeCallbacksAndMessages(null);
        if (api != null) api.close();
        network.shutdownNow();
        super.onDestroy();
    }
}
