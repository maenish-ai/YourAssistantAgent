package ai.maenish.yourassistant;

import org.json.JSONArray;
import org.json.JSONObject;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import javax.net.ssl.*;

/** Explicit QR certificate trust, scoped to one computer and each connection. */
final class HomeProfile {
    final List<String> urls=new ArrayList<>();
    final String fingerprint;
    private final SSLSocketFactory factory;

    HomeProfile(JSONObject code)throws Exception {
        fingerprint=code.getString("cert_sha256").toLowerCase(java.util.Locale.ROOT);
        if(!fingerprint.matches("[a-f0-9]{64}"))throw new IllegalArgumentException("Invalid certificate fingerprint");
        JSONArray values=code.getJSONArray("urls");if(values.length()<1||values.length()>2)throw new IllegalArgumentException();
        for(int i=0;i<values.length();i++){
            String raw=values.getString(i);URI uri=new URI(raw);
            if(!"https".equals(uri.getScheme())||uri.getHost()==null||uri.getPort()==0||uri.getPort()>65535||uri.getRawUserInfo()!=null||uri.getRawQuery()!=null||uri.getRawFragment()!=null||uri.getRawPath()!=null&&!uri.getRawPath().isEmpty())throw new IllegalArgumentException("Invalid computer address");
            if(!urls.contains(raw))urls.add(raw);
        }
        X509TrustManager trust=new X509TrustManager(){
            public X509Certificate[] getAcceptedIssuers(){return new X509Certificate[0];}
            public void checkClientTrusted(X509Certificate[] chain,String type)throws CertificateException{throw new CertificateException("Client trust is not used");}
            public void checkServerTrusted(X509Certificate[] chain,String type)throws CertificateException{verify(chain);}
        };
        SSLContext context=SSLContext.getInstance("TLS");context.init(null,new TrustManager[]{trust},new java.security.SecureRandom());factory=context.getSocketFactory();
    }
    void verify(X509Certificate[] chain)throws CertificateException {
        if(chain==null||chain.length==0)throw new CertificateException("Missing computer certificate");
        chain[0].checkValidity();
        try{
            String found=RelayCrypto.hex(MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded()));
            if(!MessageDigest.isEqual(found.getBytes(StandardCharsets.US_ASCII),fingerprint.getBytes(StandardCharsets.US_ASCII)))throw new CertificateException("Computer identity changed; scan its QR again");
        }catch(CertificateException e){throw e;}catch(Exception e){throw new CertificateException("Invalid computer identity",e);}
    }
    void apply(HttpsURLConnection connection){
        String host=connection.getURL().getHost();
        connection.setSSLSocketFactory(factory);
        connection.setHostnameVerifier((requested,session)->{
            if(!host.equalsIgnoreCase(requested))return false;
            try{verify(new X509Certificate[]{(X509Certificate)session.getPeerCertificates()[0]});return true;}catch(Exception e){return false;}
        });
    }
    String encode()throws Exception {
        JSONObject value=new JSONObject().put("urls",new JSONArray(urls)).put("cert_sha256",fingerprint);
        return "home+"+Base64.getUrlEncoder().withoutPadding().encodeToString(value.toString().getBytes(StandardCharsets.UTF_8));
    }
    static HomeProfile decode(String value)throws Exception {
        if(value.length()>4096||!value.startsWith("home+"))throw new IllegalArgumentException();
        return new HomeProfile(new JSONObject(new String(Base64.getUrlDecoder().decode(value.substring(5)),StandardCharsets.UTF_8)));
    }
}
