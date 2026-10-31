from yaa_lite.backup.crypto_backup import generate_recovery_key

def test_recovery_key_shape():
    k = generate_recovery_key()
    assert len(k) >= 40
