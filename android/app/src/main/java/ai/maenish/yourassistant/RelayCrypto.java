package ai.maenish.yourassistant;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Interoperates with relay_protocol.py; the broker has no encryption key. */
final class RelayCrypto {
    private final byte[] key;
    final String channel, desktopAuth, phoneAuth;
    RelayCrypto(String token) throws Exception {
        if(token==null||!token.matches("[A-Za-z0-9_-]{32,128}"))throw new IllegalArgumentException("Invalid pairing secret");
        key=derive("encryption",token);channel=hex(derive("channel",token)).substring(0,32);
        desktopAuth=encode(derive("desktop",token));phoneAuth=encode(derive("phone",token));
    }
    static byte[] derive(String label,String token)throws Exception{return MessageDigest.getInstance("SHA-256").digest(("yaa-relay-v1:"+label+'\0'+token).getBytes(StandardCharsets.UTF_8));}
    static String encode(byte[] data){return Base64.getUrlEncoder().withoutPadding().encodeToString(data);}
    static byte[] decode(String data){return Base64.getUrlDecoder().decode(data);}
    static String hex(byte[] data){StringBuilder result=new StringBuilder();for(byte b:data)result.append(String.format(java.util.Locale.ROOT,"%02x",b&255));return result.toString();}
    private byte[] aad(String direction,String id){
        if(!("request".equals(direction)||"response".equals(direction))||id==null||!id.matches("[A-Za-z0-9_-]{8,80}"))throw new IllegalArgumentException("Invalid envelope");
        return ("yaa-relay-v1|"+direction+"|"+channel+"|"+id).getBytes(StandardCharsets.UTF_8);
    }
    byte[] encrypt(String direction,String id,byte[] data,byte[] nonce)throws Exception{
        if(nonce.length!=12)throw new IllegalArgumentException("Invalid nonce");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(aad(direction,id));return cipher.doFinal(data);
    }
    byte[] decrypt(String direction,String id,byte[] data,byte[] nonce)throws Exception{
        if(nonce.length!=12)throw new IllegalArgumentException("Invalid nonce");
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,nonce));cipher.updateAAD(aad(direction,id));return cipher.doFinal(data);
    }
    static byte[] nonce(){byte[] value=new byte[12];new SecureRandom().nextBytes(value);return value;}
}
