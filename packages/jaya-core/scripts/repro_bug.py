
import sys
import os

try:
    print("Testing SoulCrypto (Binary)...")
    from jaya_core.brain_v2.protection.soul_crypto import SoulCrypto
    # from src.brain_v2.model.architecture import JayaHybridModel
    import numpy as np
    print("Imported numpy")
    import numba
    print("Imported numba")
    from jaya_core.brain_v2.model.ternary import TernaryLinear
    print("Imported TernaryLinear")
    
    crypto = SoulCrypto()
    # Mock derive key to set self.key (since __init__ sets default, but let's be sure)
    # in __init__: self.key = key or b'...'
    # So it has a key.
    
    data = {"state": "GENESIS_EMPTY", "memories": []}
    print(f"Encrypting: {data}")
    
    try:
        nonce, cipher, tag = crypto.encrypt(data)
        print("SoulCrypto.encrypt: PASS")
    except Exception as e:
        print(f"SoulCrypto.encrypt: FAIL - {e}")
        import traceback
        traceback.print_exc()

    print("\nTesting JayaSerializer (Binary)...")
    from jaya_core.brain_v2.format.serializer import JayaSerializer
    from jaya_core.brain_v2.format.schema import JayaHeader, JayaFlags
    
    # Mock header
    header = JayaHeader(
        flags=JayaFlags.ENCRYPTED_AES256 | JayaFlags.HAS_DNA_ANCHOR | JayaFlags.HARDWARE_LOCKED,
        hardware_hash=b"1"*32,
        dna_summary_hash=b"2"*32
    )
    # Mock body
    body = b"DUMMY_BODY"
    # Mock soul
    soul = {"state": "GENESIS_EMPTY"}
    
    serializer = JayaSerializer("pass", b"hwid_123")
    
    try:
        serializer.save_model("TEST_MODEL.jay", header, body, soul)
        print("JayaSerializer.save_model: PASS")
    except Exception as e:
        print(f"JayaSerializer.save_model: FAIL - {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"Global Fail: {e}")
    import traceback
    traceback.print_exc()
