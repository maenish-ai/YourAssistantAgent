package ai.maenish.yourassistant;

import android.app.Activity;
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
    private Button connectButton, disconnectButton, sendButton, attachButton, newChatButton;
    private LinearLayout connectionFields, transcript;
    private ScrollView scroll;
    private boolean resumed, destroyed, connected, busy, polling;
    private int generation;
    private long cursor;
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
        updateButtons();
        if (savedInstanceState != null && savedInstanceState.getBoolean("was_connected", false)
                && !tokenField.getText().toString().isEmpty()) main.post(this::connect);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        state.putBoolean("was_connected", connected);
        super.onSaveInstanceState(state);
    }

    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void buildViews() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setPadding(dp(12), dp(10), dp(12), dp(10));
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            view.setPadding(dp(12) + insets.getSystemWindowInsetLeft(), dp(10) + insets.getSystemWindowInsetTop(),
                    dp(12) + insets.getSystemWindowInsetRight(), dp(10) + insets.getSystemWindowInsetBottom());
            return insets;
        });
        setContentView(root);
        TextView title = label("مساعدك على كمبيوتر البيت", 21);
        root.addView(title);
        connectionFields = new LinearLayout(this);
        connectionFields.setOrientation(LinearLayout.VERTICAL);
        root.addView(connectionFields);
        serverField = field("رابط HTTPS الذي أعددته للكمبيوتر", false);
        serverField.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        connectionFields.addView(serverField);
        tokenField = field("رمز الاقتران من إعدادات الكمبيوتر", true);
        tokenField.setSaveEnabled(false);
        tokenField.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO);
        connectionFields.addView(tokenField);
        connectButton = button("حفظ واتصال", this::connect);
        connectionFields.addView(connectButton);
        LinearLayout connectionActions = row();
        Button showSettings = button("إعداد الاتصال", () -> connectionFields.setVisibility(
                connectionFields.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE));
        disconnectButton = button("قطع الاتصال", this::disconnect);
        connectionActions.addView(showSettings, weighted());
        connectionActions.addView(disconnectButton, weighted());
        root.addView(connectionActions);
        status = label("أدخل رابط الكمبيوتر ورمز الاقتران. التحديث يعمل أثناء فتح التطبيق.", 13);
        root.addView(status);
        scroll = new ScrollView(this);
        transcript = new LinearLayout(this);
        transcript.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(transcript);
        root.addView(scroll, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        LinearLayout taskActions = row();
        newChatButton = button("محادثة جديدة", this::newChat);
        attachButton = button("إرفاق ZIP", this::chooseZip);
        taskActions.addView(newChatButton, weighted());
        taskActions.addView(attachButton, weighted());
        root.addView(taskActions);
        composer = new EditText(this);
        composer.setHint("اكتب طلبك للمساعد…");
        composer.setMinLines(1);
        composer.setMaxLines(3);
        composer.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        root.addView(composer);
        sendButton = button("إرسال", this::sendText);
        root.addView(sendButton);
    }

    private TextView label(String text, int size) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setPadding(dp(5), dp(5), dp(5), dp(5));
        view.setTextIsSelectable(true);
        return view;
    }

    private EditText field(String hint, boolean secret) {
        EditText view = new EditText(this);
        view.setHint(hint);
        view.setSingleLine(true);
        view.setTextDirection(View.TEXT_DIRECTION_LTR);
        if (secret) view.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        return view;
    }

    private Button button(String text, Runnable action) {
        Button view = new Button(this);
        view.setText(text);
        view.setOnClickListener(v -> action.run());
        return view;
    }

    private LinearLayout row() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.HORIZONTAL);
        return view;
    }

    private LinearLayout.LayoutParams weighted() {
        return new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
    }

    private boolean current(int requestGeneration) { return !destroyed && generation == requestGeneration; }

    private void updateButtons() {
        sendButton.setEnabled(connected && !busy);
        attachButton.setEnabled(connected && !busy);
        newChatButton.setEnabled(connected && !busy);
        composer.setEnabled(connected && !busy);
        connectButton.setEnabled(!busy);
        disconnectButton.setEnabled(api != null);
    }

    private void connect() {
        final ApiClient client;
        final String url = serverField.getText().toString().trim();
        final String token = tokenField.getText().toString().trim();
        try { client = new ApiClient(url, token); }
        catch (ApiClient.ApiException e) { status.setText(e.getMessage()); return; }
        disconnect();
        api = client;
        final int requestGeneration = ++generation;
        busy = true;
        status.setText("جاري الاتصال بالكمبيوتر…");
        updateButtons();
        network.execute(() -> {
            try {
                JSONObject response = client.events(0);
                credentials.save(client.origin(), token);
                main.post(() -> {
                    if (!current(requestGeneration)) return;
                    connected = true;
                    busy = false;
                    cursor = 0;
                    usedApprovalTokens.clear();
                    transcript.removeAllViews();
                    connectionFields.setVisibility(View.GONE);
                    applyEvents(response);
                    status.setText("متصل • تستمر المهام على الكمبيوتر، وتظهر النتائج هنا أثناء فتح التطبيق.");
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
                });
            }
        });
    }

    private void disconnect() {
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
                        disconnect();
                        connectionFields.setVisibility(View.VISIBLE);
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
            cursor = id;
        }
        cursor = Math.max(cursor, response.optLong("cursor", cursor));
    }

    private void appendText(String text, String sender) {
        if (text.isEmpty()) return;
        TextView view = label(sender + "\n" + text, 16);
        view.setBackgroundColor("أنت".equals(sender) ? Color.rgb(228, 239, 255) : Color.rgb(242, 244, 247));
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
        if (text.length() > 12000) { status.setText("اختصر الرسالة إلى 12000 حرف أو أقل."); return; }
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
        schedulePoll();
    }

    @Override protected void onPause() {
        resumed = false;
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
