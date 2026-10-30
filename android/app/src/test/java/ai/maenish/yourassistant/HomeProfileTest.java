package ai.maenish.yourassistant;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import javax.net.ssl.*;
import java.io.*;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk=28)
public class HomeProfileTest {
    private static final String TOKEN="A".repeat(43);
    private KeyStore keys()throws Exception{
        KeyStore store=KeyStore.getInstance("PKCS12");
        try(InputStream input=getClass().getResourceAsStream("/home-test-only.p12")){store.load(input,"test-only".toCharArray());}
        return store;
    }
    private JSONObject code(String... urls)throws Exception{
        X509Certificate cert=(X509Certificate)keys().getCertificate("home-test");
        return new JSONObject().put("urls",new JSONArray(urls)).put("cert_sha256",RelayCrypto.hex(MessageDigest.getInstance("SHA-256").digest(cert.getEncoded())));
    }
    @Test public void productionPythonQrDecodesToDirectPairingProfile()throws Exception{
        try(DataInputStream input=new DataInputStream(getClass().getResourceAsStream("/home-qr-test-only.gray"))){
            int width=input.readInt(),height=input.readInt();int[] pixels=new int[width*height];
            for(int i=0;i<pixels.length;i++){int gray=input.readUnsignedByte();pixels[i]=(gray<<16)|(gray<<8)|gray;}
            com.google.zxing.BinaryBitmap bitmap=new com.google.zxing.BinaryBitmap(new com.google.zxing.common.HybridBinarizer(new com.google.zxing.RGBLuminanceSource(width,height,pixels)));
            String raw=new com.google.zxing.qrcode.QRCodeReader().decode(bitmap).getText();JSONObject code=new JSONObject(raw);
            assertEquals("yaa-direct",code.getString("type"));assertEquals(1,code.getInt("v"));assertEquals(TOKEN,code.getString("token"));
            HomeProfile profile=new HomeProfile(code);assertEquals("https://192.168.1.50:8443",profile.urls.get(0));
            assertTrue(ApiClient.automaticOrigin(profile.encode()));
        }
    }
    @Test public void profileRoundTripRejectsUntrustedEndpointsAndWrongIdentity()throws Exception{
        HomeProfile profile=new HomeProfile(code("https://192.168.1.10:8443","https://computer.example:8443"));
        assertEquals(profile.urls,HomeProfile.decode(profile.encode()).urls);
        X509Certificate cert=(X509Certificate)keys().getCertificate("home-test");profile.verify(new X509Certificate[]{cert});
        HomeProfile wrong=new HomeProfile(code("https://127.0.0.1:8443").put("cert_sha256","0".repeat(64)));
        try{wrong.verify(new X509Certificate[]{cert});fail("Wrong identity accepted");}catch(CertificateException expected){}
        for(String url:new String[]{"http://192.168.1.10:8443","https://user:pass@pc.test","https://pc.test/path","https://pc.test?secret=value","https://pc.test#fragment","https://pc.test:0"}){
            try{new HomeProfile(code(url));fail("Unsafe origin accepted");}catch(Exception expected){}
        }
    }
    @Test public void liveHttpsFallsBackToReachableAddressAndRejectsWrongCertificate()throws Exception{
        try(LocalServer server=new LocalServer(false)){
            HomeProfile profile=new HomeProfile(code("https://127.0.0.1:1",server.url()));
            ApiClient client=new ApiClient(profile.encode(),TOKEN);
            try{
                assertEquals(0,client.events(0).getLong("cursor"));
                assertEquals("accepted",client.post("/v1/messages",new JSONObject().put("text","hello")).getString("job_id"));
            }finally{client.close();}
            assertEquals(1,server.posts.get());int handled=server.handled.get();
            HomeProfile wrong=new HomeProfile(code(server.url()).put("cert_sha256","0".repeat(64)));
            ApiClient rejected=new ApiClient(wrong.encode(),TOKEN);
            try{rejected.events(0);fail("TLS accepted wrong computer");}catch(ApiClient.ApiException expected){}finally{rejected.close();}
            assertEquals(handled,server.handled.get());
        }
    }
    @Test public void uncertainPostIsNeverReplayedAtAnotherAddress()throws Exception{
        try(LocalServer server=new LocalServer(true)){
            ApiClient client=new ApiClient(new HomeProfile(code(server.url(),"https://127.0.0.1:1")).encode(),TOKEN);
            try{
                client.events(0);
                try{client.post("/v1/messages",new JSONObject().put("text","once"));fail("Dropped response should fail");}catch(ApiClient.ApiException expected){}
            }finally{client.close();}
            assertEquals(1,server.posts.get());
        }
    }
    /** Public test-only PKCS12 fixture. Never used by a distributed application. */
    private final class LocalServer implements AutoCloseable{
        final SSLServerSocket socket;final Thread thread;volatile boolean stopped;
        final AtomicInteger posts=new AtomicInteger(),handled=new AtomicInteger();
        LocalServer(boolean dropPost)throws Exception{
            KeyManagerFactory managers=KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());managers.init(keys(),"test-only".toCharArray());
            SSLContext context=SSLContext.getInstance("TLS");context.init(managers.getKeyManagers(),null,null);
            socket=(SSLServerSocket)context.getServerSocketFactory().createServerSocket(0,8,InetAddress.getByName("127.0.0.1"));
            thread=new Thread(()->{
                while(!stopped)try(SSLSocket peer=(SSLSocket)socket.accept()){
                    peer.setSoTimeout(5000);BufferedReader input=new BufferedReader(new InputStreamReader(peer.getInputStream(),StandardCharsets.UTF_8));
                    String request=input.readLine();if(request==null)continue;
                    boolean authorized=false;int length=0;String header;
                    while((header=input.readLine())!=null&&!header.isEmpty()){
                        if(header.equals("Authorization: Bearer "+TOKEN))authorized=true;
                        if(header.toLowerCase(java.util.Locale.ROOT).startsWith("content-length:"))length=Integer.parseInt(header.substring(15).trim());
                    }
                    if(!authorized)throw new IOException("Test client omitted authentication");
                    for(int i=0;i<length;i++)if(input.read()<0)throw new EOFException();
                    handled.incrementAndGet();boolean post=request.startsWith("POST");
                    if(post){posts.incrementAndGet();if(dropPost)continue;}
                    String json=post?"{\"job_id\":\"accepted\"}":request.contains("/events?")?"{\"events\":[],\"cursor\":0}":"{\"desktop\":false}";
                    byte[] bytes=json.getBytes(StandardCharsets.UTF_8);OutputStream output=peer.getOutputStream();
                    output.write(("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "+bytes.length+"\r\nConnection: close\r\n\r\n").getBytes(StandardCharsets.US_ASCII));output.write(bytes);output.flush();
                }catch(Exception ignored){}
            },"home-https-test");thread.setDaemon(true);thread.start();
        }
        String url(){return "https://127.0.0.1:"+socket.getLocalPort();}
        public void close()throws Exception{stopped=true;socket.close();thread.join(2000);}
    }
}
