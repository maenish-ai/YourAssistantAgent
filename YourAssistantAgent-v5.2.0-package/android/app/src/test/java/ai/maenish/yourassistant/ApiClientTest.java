package ai.maenish.yourassistant;

import org.junit.Test;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.fail;

/** Constructor tests do not open sockets or require an Android device. */
public class ApiClientTest {
    private static final String TOKEN = "owner-pairing-token_012345678901234567890123456789";

    @Test public void acceptsAndNormalizesHttpsOrigin() throws Exception {
        assertEquals("https://home.example.test", new ApiClient("https://home.example.test/", TOKEN).origin());
        assertEquals("https://home.example.test:8443", new ApiClient("https://home.example.test:8443", TOKEN).origin());
    }

    @Test public void rejectsUnsafeOrAmbiguousOrigins() {
        String[] invalid = {
            "http://home.example.test", "https://user:password@home.example.test",
            "https://home.example.test/api", "https://home.example.test?key=value",
            "https://home.example.test/#fragment", "https://home.example.test//",
            "https:///missing-host", "file:///secret", "home.example.test"
            ,"https://home.example.test:0", "https://home.example.test:65536"
        };
        for (String origin : invalid) {
            try {
                new ApiClient(origin, TOKEN);
                fail("Should reject origin: " + origin);
            } catch (ApiClient.ApiException expected) { /* no network was attempted */ }
        }
    }

    @Test public void relayModeKeepsDistinctTransportAndValidatesCredentials() throws Exception {
        assertEquals("relay+https://relay.example.test",new ApiClient("relay+https://relay.example.test",TOKEN).origin());
        for(String origin:new String[]{"relay+http://relay.example.test","relay+https://relay.example.test/api","relay+https://user:password@relay.example.test","relay+https://relay.example.test:65536"}){
            try{new ApiClient(origin,TOKEN);fail("Invalid relay accepted");}catch(ApiClient.ApiException expected){}
        }
        try{new ApiClient("relay+https://relay.example.test","short");fail("Invalid relay credential accepted");}catch(ApiClient.ApiException expected){}
    }

    @Test public void requiresExactPairingTokenFormat() {
        String[] invalid = {"", "short", "x".repeat(31), "x".repeat(129), TOKEN + "\n", " " + TOKEN, TOKEN + ":"};
        for (String token : invalid) {
            try {
                new ApiClient("https://home.example.test", token);
                fail("Should reject an invalid pairing token");
            } catch (ApiClient.ApiException expected) { /* invalid credential rejected */ }
        }
    }
}
