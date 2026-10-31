package ai.maenish.yourassistant;

import org.json.JSONObject;
import java.io.*;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import javax.net.ssl.HttpsURLConnection;

/** End-to-end encrypted RPC and chunked file transport over an opaque HTTPS relay. */
final class RelayTransport {
    private static final int CHUNK=512*1024;
    private final String url,token;
    private final RelayCrypto crypto;
    private volatile boolean closed;
    private ApiClient.Progress progress=(done,total)->{};
    void progress(ApiClient.Progress listener){progress=listener;}
    private final AtomicReference<HttpsURLConnection> active=new AtomicReference<>();
    RelayTransport(String url,String token)throws ApiClient.ApiException {
        try{
            URI uri=new URI(url);
            if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||uri.getPort()>65535||uri.getPort()==0||uri.getRawUserInfo()!=null||uri.getRawQuery()!=null||uri.getRawFragment()!=null||uri.getRawPath()!=null&&!uri.getRawPath().isEmpty()&&!"/".equals(uri.getRawPath()))throw new Exception();
            this.url=url.endsWith("/")?url.substring(0,url.length()-1):url;this.token=token;crypto=new RelayCrypto(token);
        }catch(Exception e){throw new ApiClient.ApiException("رمز الاقتران لا يحتوي خادماً صالحاً. امسح QR من برنامج الكمبيوتر.");}
    }
    private String base(){return url+"/relay/v1/"+crypto.channel;}
    void close(){closed=true;HttpsURLConnection connection=active.getAndSet(null);if(connection!=null)connection.disconnect();}
    private static final class Response {int status;JSONObject value;Response(int s,JSONObject v){status=s;value=v;}}
    private Response web(String method,String address,JSONObject body)throws Exception {
        if(closed)throw new IOException("closed");
        HttpsURLConnection connection=(HttpsURLConnection)new URL(address).openConnection();active.set(connection);
        try{
            if(closed)throw new IOException("closed");
            connection.setInstanceFollowRedirects(false);connection.setConnectTimeout(10000);connection.setReadTimeout(23000);
            connection.setRequestMethod(method);connection.setRequestProperty("Authorization","Bearer "+crypto.phoneAuth);
            connection.setRequestProperty("Accept","application/json");
            if(body!=null){byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8);connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json");connection.setFixedLengthStreamingMode(bytes.length);try(OutputStream output=connection.getOutputStream()){output.write(bytes);}}
            int status=connection.getResponseCode();InputStream stream=status<400?connection.getInputStream():connection.getErrorStream();
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            if(stream!=null)try(InputStream input=stream){byte[] buffer=new byte[65536];int count;while((count=input.read(buffer))!=-1){if(bytes.size()+count>4*1024*1024)throw new IOException("limit");bytes.write(buffer,0,count);}}
            JSONObject value=bytes.size()==0?new JSONObject():new JSONObject(bytes.toString("UTF-8"));return new Response(status,value);
        }finally{active.compareAndSet(connection,null);connection.disconnect();}
    }
    private JSONObject rpc(String op,JSONObject args)throws ApiClient.ApiException {
        try{
            String id=UUID.randomUUID().toString().replace("-","");byte[] nonce=RelayCrypto.nonce();
            JSONObject request=new JSONObject().put("time",System.currentTimeMillis()/1000.0).put("op",op).put("args",args);
            byte[] encrypted=crypto.encrypt("request",id,request.toString().getBytes(StandardCharsets.UTF_8),nonce);
            JSONObject envelope=new JSONObject().put("v",1).put("id",id).put("nonce",RelayCrypto.encode(nonce)).put("ciphertext",RelayCrypto.encode(encrypted));
            long deadline=System.nanoTime()+70_000_000_000L;boolean submit=true;
            while(!closed&&System.nanoTime()<deadline){
                if(submit){Response sent=web("POST",base()+"/requests",envelope);if(sent.status!=202)throw serverError(sent.status,sent.value);submit=false;}
                Response response=web("GET",base()+"/requests/"+id,null);
                if(response.status==202){submit=true;continue;}
                if(response.status!=200)throw serverError(response.status,response.value);
                JSONObject value=response.value;
                if(value.optInt("v")!=1||!id.equals(value.optString("id")))throw new IOException("mismatch");
                JSONObject result=new JSONObject(new String(crypto.decrypt("response",id,RelayCrypto.decode(value.getString("ciphertext")),RelayCrypto.decode(value.getString("nonce"))),StandardCharsets.UTF_8));
                try{web("DELETE",base()+"/requests/"+id,null);}catch(Exception ignored){}
                if(!result.optBoolean("ok")){
                    String reason=result.optString("error","");
                    String message=reason.contains("request_expired")?"اضبط وقت وتاريخ الهاتف والكمبيوتر ثم أعد الاتصال.":
                        reason.contains("already_processed")?"سبق أن وصل الطلب. راجع المحادثة أو الشاشة قبل تكراره.":
                        reason.contains("destination_exists")?"يوجد ملف بنفس الاسم أو المجلد غير صالح. اختر اسماً آخر.":
                        reason.contains("integrity")?"تعذر التحقق من اكتمال الملف. أعد النقل.":
                        reason.contains("too_many")?"انتظر انتهاء نقل الملفات السابق ثم أعد المحاولة.":
                        "تعذر إكمال الطلب على الكمبيوتر. راجع المحادثة قبل تكراره.";
                    throw new ApiClient.ApiException(message);
                }
                return result;
            }
            throw new ApiClient.ApiException("الكمبيوتر لم يرد. الاتصال يُعاد تلقائياً؛ افحص المحادثة قبل تكرار أمر قد يكون وصل.");
        }catch(ApiClient.ApiException e){throw e;}
        catch(Exception e){throw new ApiClient.ApiException("انقطع الربط المشفّر. افحص تشغيل الكمبيوتر والخادم؛ راجع المحادثة قبل تكرار الطلب.");}
    }
    private ApiClient.ApiException serverError(int status,JSONObject value){
        String message=status==503?"كمبيوتر البيت غير متصل حالياً. سيُعاد الاتصال تلقائياً.":status==403?"الربط غير جاهز أو تغيّر مفتاح الاقتران. تأكد من تشغيل البرنامج أو امسح QR الجديد.":"تعذر الوصول لخادم الربط (HTTP "+status+").";
        return new ApiClient.ApiException(message,status);
    }
    private JSONObject payload(JSONObject response)throws ApiClient.ApiException {
        try{
            int status=response.getInt("status");byte[] bytes=RelayCrypto.decode(response.getString("body"));
            if(bytes.length>2*1024*1024)throw new IOException();
            JSONObject value=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
            if(status<200||status>=300)throw new ApiClient.ApiException(value.optString("error","تعذر تنفيذ الطلب على الكمبيوتر.").replace(token,"[hidden]"),status);
            return value;
        }catch(ApiClient.ApiException e){throw e;}catch(Exception e){throw new ApiClient.ApiException("رد غير صالح من برنامج الكمبيوتر.");}
    }
    JSONObject http(String method,String path,byte[] body)throws ApiClient.ApiException {
        try{return payload(rpc("http",new JSONObject().put("method",method).put("path",path).put("body",RelayCrypto.encode(body==null?new byte[0]:body))));}
        catch(ApiClient.ApiException e){throw e;}catch(Exception e){throw new ApiClient.ApiException("تعذر تجهيز الطلب.");}
    }
    JSONObject upload(File file,String path,String mime)throws ApiClient.ApiException {
        try{
            JSONObject start=rpc("upload_start",new JSONObject().put("path",path).put("mime",mime).put("size",file.length()));String transfer=start.getString("transfer");
            MessageDigest hash=MessageDigest.getInstance("SHA-256");long offset=0;
            try(InputStream input=new FileInputStream(file)){byte[] buffer=new byte[CHUNK];int count;
                while((count=input.read(buffer))!=-1){if(closed)throw new IOException();byte[] block=java.util.Arrays.copyOf(buffer,count);hash.update(block);
                    JSONObject result=rpc("upload_chunk",new JSONObject().put("transfer",transfer).put("offset",offset).put("data",RelayCrypto.encode(block)));
                    offset+=count;if(result.getLong("offset")!=offset)throw new IOException();progress.update(offset,file.length());
                }
            }
            return payload(rpc("upload_finish",new JSONObject().put("transfer",transfer).put("sha256",RelayCrypto.hex(hash.digest()))));
        }catch(ApiClient.ApiException e){throw e;}catch(Exception e){throw new ApiClient.ApiException("تعذر نقل الملف عبر الربط المشفّر. افحص المحادثة قبل إعادة الإرسال.");}
    }
    void download(String path,OutputStream output)throws ApiClient.ApiException {
        try{
            JSONObject start=rpc("download_start",new JSONObject().put("path",path));String transfer=start.getString("transfer");long size=start.getLong("size");
            if(size<0||size>256L*1024*1024)throw new IOException();
            MessageDigest hash=MessageDigest.getInstance("SHA-256");long offset=0;
            while(!closed){JSONObject result=rpc("download_chunk",new JSONObject().put("transfer",transfer).put("offset",offset));
                byte[] block=RelayCrypto.decode(result.getString("data"));if(result.getLong("offset")!=offset||block.length>CHUNK||offset+block.length>size)throw new IOException();
                output.write(block);hash.update(block);offset+=block.length;progress.update(offset,size);
                if(result.optBoolean("done")){if(offset!=size||!RelayCrypto.hex(hash.digest()).equals(result.getString("sha256")))throw new IOException();return;}
                if(block.length==0)throw new IOException();
            }
            throw new IOException();
        }catch(ApiClient.ApiException e){throw e;}catch(Exception e){throw new ApiClient.ApiException("التنزيل لم يكتمل؛ قد يوجد ملف جزئي في المكان الذي اخترته.");}
    }
}
