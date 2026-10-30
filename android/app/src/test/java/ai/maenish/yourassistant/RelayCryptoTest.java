package ai.maenish.yourassistant;
import org.junit.Test;
import java.nio.charset.StandardCharsets;
import static org.junit.Assert.*;

public class RelayCryptoTest {
    @Test public void matchesPythonEnvelopeVector()throws Exception{
        RelayCrypto keys=new RelayCrypto("A".repeat(43));
        assertEquals("ec5631b9363f44ff891f50059b369184",keys.channel);
        assertEquals("01gtYqevY0uUgT4MmagzkjM0CoK1sbtbai4NFb1UoCQ",keys.phoneAuth);
        byte[] ciphertext=keys.encrypt("request","test-request-0001","hello".getBytes(StandardCharsets.UTF_8),new byte[12]);
        assertEquals("xcmoYpEA9_xu_a66Kxcx3Aq2p0VI",RelayCrypto.encode(ciphertext));
        assertEquals("hello",new String(keys.decrypt("request","test-request-0001",ciphertext,new byte[12]),StandardCharsets.UTF_8));
    }
    @Test public void rejectsChangedDirectionIdAndData()throws Exception{
        RelayCrypto keys=new RelayCrypto("B".repeat(43));byte[] nonce=RelayCrypto.nonce();byte[] sealed=keys.encrypt("request","request-00000001",new byte[]{1,2,3},nonce);
        try{keys.decrypt("response","request-00000001",sealed,nonce);fail("wrong direction accepted");}catch(javax.crypto.AEADBadTagException expected){}
        try{keys.decrypt("request","request-00000002",sealed,nonce);fail("wrong ID accepted");}catch(javax.crypto.AEADBadTagException expected){}
        sealed[0]^=1;
        try{keys.decrypt("request","request-00000001",sealed,nonce);fail("tampering accepted");}catch(javax.crypto.AEADBadTagException expected){}
    }
    @Test public void roleSecretsAreNotEncryptionKeys()throws Exception{
        RelayCrypto keys=new RelayCrypto("C".repeat(43));
        assertNotEquals(keys.phoneAuth,keys.desktopAuth);
        assertNotEquals(keys.phoneAuth,RelayCrypto.encode(RelayCrypto.derive("encryption","C".repeat(43))));
    }
}
