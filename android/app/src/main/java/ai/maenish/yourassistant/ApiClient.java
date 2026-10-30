package ai.maenish.yourassistant;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import javax.net.ssl.HttpsURLConnection;

/** HTTPS only, platform TLS verification, no redirects and no automatic POST retries. */
final class ApiClient {
    static final long MAX_UPLOAD_BYTES = 20L * 1024 * 1024;
    private static final int MAX_RESPONSE_BYTES = 2 * 1024 * 1024;
    private final String baseUrl;
    private final String token;
    private RelayTransport relay;
    private HomeProfile home;
    private String selectedOrigin;
    static boolean automaticOrigin(String url){return url!=null&&(url.startsWith("home+")||url.startsWith("relay+https://"));}
    private final AtomicReference<HttpsURLConnection> active = new AtomicReference<>();
    private volatile boolean closed;
    interface Progress { void update(long transferred,long total); }
    private Progress progress=(done,total)->{};
    void progress(Progress listener){progress=listener;if(relay!=null)relay.progress(listener);}

    static final class ApiException extends Exception {
        final int status;
        ApiException(String message) { this(message, -1); }
        ApiException(String message, int status) { super(message); this.status = status; }
    }

    ApiClient(String url, String token) throws ApiException {
        if(url!=null&&url.startsWith("home+")){
            try{
                if(token==null||!token.matches("[A-Za-z0-9_-]{32,128}"))throw new Exception();
                home=HomeProfile.decode(url);this.baseUrl=home.encode();this.token=token;return;
            }catch(Exception e){throw new ApiException("امسح QR المباشر من برنامج الكمبيوتر مرة أخرى؛ بيانات الربط غير صالحة.");}
        }
        if(url!=null && url.startsWith("relay+https://")){
            relay=new RelayTransport(url.substring(6),token);this.baseUrl=url;this.token=token;return;
        }
        try {
            URI parsed = new URI(url.trim());
            if (!"https".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null ||
                    parsed.getPort() == 0 || parsed.getPort() > 65535 ||
                    parsed.getRawUserInfo() != null || parsed.getRawQuery() != null || parsed.getRawFragment() != null ||
                    (parsed.getRawPath() != null && !parsed.getRawPath().isEmpty() && !"/".equals(parsed.getRawPath()))) {
                throw new IllegalArgumentException();
            }
            String normalized = parsed.toASCIIString();
            while (normalized.endsWith("/")) normalized = normalized.substring(0, normalized.length() - 1);
            baseUrl = normalized;
        } catch (Exception e) {
            throw new ApiException("أدخل رابط HTTPS صحيحاً لكمبيوتر البيت، بدون اسم مستخدم أو معاملات إضافية.");
        }
        if (token == null || !token.matches("[A-Za-z0-9_-]{32,128}")) {
            throw new ApiException("أدخل رمز الاقتران الذي يظهر في إعدادات برنامج الكمبيوتر.");
        }
        this.token = token.trim();
    }

    String origin() { return baseUrl; }

    JSONObject events(long after) throws ApiException {
        JSONObject response = request("GET", "/v1/events?after=" + Math.max(0, after), null, null, null);
        if (response.optJSONArray("events") == null || response.optLong("cursor", -1) < 0) {
            throw new ApiException("رابط HTTPS لا يشير إلى خدمة المساعد الصحيحة.");
        }
        return response;
    }

    JSONObject post(String path, JSONObject payload) throws ApiException {
        byte[] bytes = payload.toString().getBytes(StandardCharsets.UTF_8);
        return request("POST", path, bytes, null, UUID.randomUUID().toString());
    }

    JSONObject upload(File file) throws ApiException {
        if (file.length() <= 0 || file.length() > MAX_UPLOAD_BYTES) {
            throw new ApiException("حجم ZIP المسموح يصل إلى 20 MiB.");
        }
        return request("POST", "/v1/uploads", null, file, UUID.randomUUID().toString());
    }

    JSONObject desktop() throws ApiException { return request("GET", "/v1/desktop", null, null, null); }
    JSONObject capabilities() throws ApiException { return request("GET", "/v1/capabilities", null, null, null); }
    JSONObject files(String path) throws ApiException {
        return request("GET", "/v1/files?path=" + encode(path), null, null, null);
    }
    static String encode(String value) {
        try { return java.net.URLEncoder.encode(value, "UTF-8"); }
        catch (Exception e) { throw new IllegalArgumentException("Invalid path"); }
    }
    JSONObject uploadFile(File file, String folder, String name) throws ApiException {
        if (file.length() > 256L * 1024 * 1024) throw new ApiException("الملف يتجاوز 256 MiB.");
        return request("POST", "/v1/files/upload?folder=" + encode(folder) + "&name=" + encode(name),
                null, file, UUID.randomUUID().toString(), "application/octet-stream");
    }
    void downloadFile(String path, OutputStream output) throws ApiException {
        if(relay!=null){relay.download(path,output);return;}
        HttpsURLConnection connection = null;
        try {
            ensureHomeOrigin();
            if (closed) throw new ApiException("انقطع الاتصال.");
            connection = (HttpsURLConnection) new URL((home==null?baseUrl:selectedOrigin) + "/v1/files/download?path=" + encode(path)).openConnection();
            active.set(connection);
            if(home!=null)home.apply(connection);
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(home==null?10000:5000); connection.setReadTimeout(35000);
            connection.setRequestProperty("Authorization", "Bearer " + token);
            int status = connection.getResponseCode();
            if (status != 200) throw new ApiException("تعذر تنزيل الملف (HTTP " + status + ").", status);
            long expected = connection.getContentLengthLong();
            if (expected < 0 || expected > 256L * 1024 * 1024) throw new ApiException("حجم الملف غير صالح أو يتجاوز 256 MiB.");
            long received = 0;
            try (InputStream input = connection.getInputStream()) {
                byte[] buffer = new byte[65536]; int count;
                while ((count = input.read(buffer)) != -1) {
                    received += count;
                    if (closed || received > expected) throw new ApiException("أُلغي التنزيل أو تغير حجم الملف.");
                    output.write(buffer, 0, count);progress.update(received,expected);
                }
            }
            if (received != expected) throw new ApiException("التنزيل غير مكتمل. أعد المحاولة.");
        } catch (ApiException e) { throw e; }
        catch (Exception e) { throw new ApiException("تعذر نقل الملف إلى الهاتف؛ قد يوجد ملف جزئي في المكان الذي اخترته."); }
        finally { if (connection != null) { active.compareAndSet(connection,null); connection.disconnect(); } }
    }

    void close() {
        closed = true;
        if(relay!=null)relay.close();
        HttpsURLConnection connection = active.getAndSet(null);
        if (connection != null) connection.disconnect();
    }

    private JSONObject request(String method, String path, byte[] bytes, File file, String requestId)
            throws ApiException {
        return request(method, path, bytes, file, requestId, "application/zip");
    }

    private JSONObject request(String method, String path, byte[] bytes, File file, String requestId, String uploadMime)
            throws ApiException {
        if(relay!=null){
            if(closed)throw new ApiException("انقطع الاتصال.");
            JSONObject response=file==null?relay.http(method,path,bytes):relay.upload(file,path,uploadMime);
            if("POST".equals(method)&&response.optString("job_id","").isEmpty())throw new ApiException("الرد غير مكتمل؛ افحص المحادثة قبل إعادة الإرسال.");
            return response;
        }
        if(home!=null&&"GET".equals(method))return homeGet(path);
        ensureHomeOrigin();
        return requestAt(home==null?baseUrl:selectedOrigin,method,path,bytes,file,requestId,uploadMime);
    }

    private void ensureHomeOrigin()throws ApiException {
        if(home!=null&&selectedOrigin==null)homeGet("/v1/capabilities");
    }
    private JSONObject homeGet(String path)throws ApiException {
        java.util.List<String> candidates=new java.util.ArrayList<>();
        if(selectedOrigin!=null)candidates.add(selectedOrigin);
        for(String url:home.urls)if(!candidates.contains(url))candidates.add(url);
        for(String url:candidates){
            try{JSONObject result=requestAt(url,"GET",path,null,null,null,"application/json");selectedOrigin=url;return result;}
            catch(ApiException e){if(e.status>=0||closed)throw e;}
        }
        selectedOrigin=null;
        throw new ApiException("تعذر الوصول المباشر للكمبيوتر. داخل البيت افحص Wi-Fi والجدار الناري؛ من الخارج افحص عنوان الراوتر وتوجيه المنفذ. تحقق أيضاً من وقت الجهازين وهوية QR.");
    }
    private JSONObject requestAt(String address,String method,String path,byte[] bytes,File file,String requestId,String uploadMime)throws ApiException {
        HttpsURLConnection connection = null;
        try {
            if (closed) throw new ApiException("انقطع الاتصال؛ أعد الربط أولاً.");
            connection = (HttpsURLConnection) new URL(address + path).openConnection();
            active.set(connection);
            if (closed) throw new ApiException("انقطع الاتصال؛ أعد الربط أولاً.");
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(home==null?10000:5000);
            connection.setReadTimeout(35000);
            if(home!=null)home.apply(connection);
            connection.setRequestMethod(method);
            connection.setRequestProperty("Authorization", "Bearer " + token);
            connection.setRequestProperty("Accept", "application/json");
            if (requestId != null) connection.setRequestProperty("X-Request-ID", requestId);
            if ("POST".equals(method)) {
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", file == null ? "application/json; charset=utf-8" : uploadMime);
                connection.setFixedLengthStreamingMode(file == null ? bytes.length : file.length());
                try (OutputStream output = connection.getOutputStream()) {
                    if (file == null) {
                        output.write(bytes);
                    } else {
                        try (InputStream input = new FileInputStream(file)) {
                            byte[] buffer = new byte[65536];
                            int count;
                            long written = 0;
                            while ((count = input.read(buffer)) != -1) {
                                written += count;
                                if (written > ("application/zip".equals(uploadMime) ? MAX_UPLOAD_BYTES : 256L * 1024 * 1024) || closed) throw new ApiException("أُلغي إرسال الملف.");
                                output.write(buffer, 0, count);progress.update(written,file.length());
                            }
                        }
                    }
                }
            }
            int status = connection.getResponseCode();
            InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
            JSONObject response;
            try {
                response = new JSONObject(readResponse(stream));
            } catch (ApiException e) {
                throw e;
            } catch (Exception e) {
                if (status < 200 || status >= 300) throw new ApiException("تعذر تنفيذ الطلب (HTTP " + status + ").", status);
                throw new ApiException("رد غير صالح من خدمة الكمبيوتر. افحص عنوان الاتصال.");
            }
            if (status < 200 || status >= 300) {
                String error = response.optString("error", "");
                if (status == 404 && (path.startsWith("/v1/desktop") || path.startsWith("/v1/files")))
                    error = "حدّث برنامج الكمبيوتر إلى نسخة 4.5 أو أحدث لتفعيل التحكم والملفات.";
                if (error.isEmpty()) error = "تعذر تنفيذ الطلب (HTTP " + status + ").";
                error = error.replace(token, "[hidden]");
                throw new ApiException(error.substring(0, Math.min(400, error.length())), status);
            }
            if ("POST".equals(method) && response.optString("job_id", "").isEmpty()) {
                throw new ApiException("رد الكمبيوتر غير مكتمل؛ افحص حالة الطلب قبل إعادة إرساله.");
            }
            return response;
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            // URL/request exceptions can contain the address or credential. Only
            // display a fixed message; never log exception objects or headers.
            throw new ApiException("تعذر الاتصال. افحص الإنترنت ورابط HTTPS وتشغيل برنامج الكمبيوتر. " +
                    ("POST".equals(method) ? "إذا أرسلت أمراً، راجع المحادثة قبل تكراره؛ قد يكون وصل للكمبيوتر." : ""));
        } finally {
            if (connection != null) {
                active.compareAndSet(connection, null);
                connection.disconnect();
            }
        }
    }

    private String readResponse(InputStream stream) throws Exception {
        if (stream == null) return "{}";
        try (InputStream input = stream; ByteArrayOutputStream bytes = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (bytes.size() + count > MAX_RESPONSE_BYTES) throw new ApiException("رد الكمبيوتر أكبر من الحد المسموح.");
                bytes.write(buffer, 0, count);
            }
            return bytes.toString(StandardCharsets.UTF_8.name());
        }
    }
}
