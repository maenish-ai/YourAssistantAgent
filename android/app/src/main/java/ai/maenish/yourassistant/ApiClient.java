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
    private final AtomicReference<HttpsURLConnection> active = new AtomicReference<>();
    private volatile boolean closed;

    static final class ApiException extends Exception {
        final int status;
        ApiException(String message) { this(message, -1); }
        ApiException(String message, int status) { super(message); this.status = status; }
    }

    ApiClient(String url, String token) throws ApiException {
        try {
            URI parsed = new URI(url.trim());
            if (!"https".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null ||
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

    void close() {
        closed = true;
        HttpsURLConnection connection = active.getAndSet(null);
        if (connection != null) connection.disconnect();
    }

    private JSONObject request(String method, String path, byte[] bytes, File file, String requestId)
            throws ApiException {
        HttpsURLConnection connection = null;
        try {
            if (closed) throw new ApiException("انقطع الاتصال؛ أعد الربط أولاً.");
            connection = (HttpsURLConnection) new URL(baseUrl + path).openConnection();
            active.set(connection);
            if (closed) throw new ApiException("انقطع الاتصال؛ أعد الربط أولاً.");
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(35000);
            connection.setRequestMethod(method);
            connection.setRequestProperty("Authorization", "Bearer " + token);
            connection.setRequestProperty("Accept", "application/json");
            if (requestId != null) connection.setRequestProperty("X-Request-ID", requestId);
            if ("POST".equals(method)) {
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", file == null ? "application/json; charset=utf-8" : "application/zip");
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
                                if (written > MAX_UPLOAD_BYTES || closed) throw new ApiException("أُلغي إرسال الملف.");
                                output.write(buffer, 0, count);
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
