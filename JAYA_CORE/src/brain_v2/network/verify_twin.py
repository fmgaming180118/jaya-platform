
import asyncio
import logging
import sys
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))
from src.brain_v2.network.twin_socket import TwinSocket
from src.brain_v2.protection.crypto import CryptoSkin
from src.core_config import core_config

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TwinVerify")

async def run_simulation():
    print("--- Verifying Phase 4: The Twin Protocol ---")

    crypto = CryptoSkin()
    password = core_config.SOUL_PASSWORD

    # 1. Create Server Twin (Instance A)
    twin_a = TwinSocket(hardware_id=b"SERVER_HWID", crypto=crypto, password=password)
    twin_a.port = 7777

    # 2. Start Server
    server_task = asyncio.create_task(twin_a.start_server())
    await asyncio.sleep(1) # Wait for server boot

    # 3. Create Client Twin (Instance B)
    twin_b = TwinSocket(hardware_id=b"CLIENT_HWID", crypto=crypto, password=password)
    twin_b.port = 7777 # Connect to same port

    # 4. Connect B -> A
    print("[*] Connecting Twin B -> Twin A...")
    try:
        # In real methods, connect_to_peer uses self.port for destination,
        # but here we mock connection logic slightly differently or reuse it.
        # Since connect_to_peer opens connection to (ip, self.port),
        # and self.port is 7777, it works.

        # We need to manually handle the connection in this script or modify TwinSocket to be flexible.
        # TwinSocket currently uses self.port for both bind and connect.

        reader, writer = await asyncio.open_connection("127.0.0.1", 7777)
        print("[+] Connection Established!")

        # Manually Send Handshake from B
        handshake = {
            "type": "HANDSHAKE",
            "sender": "TWIN_B",
            "msg": "Hello Brother."
        }

        # Encrypt & Send
        # We reuse twin_b's crypto context
        import json
        session_key = twin_b.session_key
        encrypted = crypto.encrypt_soul(json.dumps(handshake).encode(), session_key)

        import struct
        msg = struct.pack('!I', len(encrypted)) + encrypted
        writer.write(msg)
        await writer.drain()
        print("[+] Encrypted Handshake Sent.")

        # 5. Verify A received it?
        # We need a callback on A
        received_event = asyncio.Event()

        async def on_message_a(payload, addr):
            print(f"[Twin A] RECEIVED PAYLOAD: {payload}")
            received_event.set()

        twin_a.on_message_callback = on_message_a

        # Wait for A to process
        try:
            await asyncio.wait_for(received_event.wait(), timeout=5.0)
            print("[PASS] Twin A successfully received and decrypted message.")
        except asyncio.TimeoutError:
            print("[FAIL] Twin A timed out waiting for message.")

    except Exception as e:
        print(f"[FAIL] Connection Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        twin_a.stop()
        server_task.cancel()

if __name__ == "__main__":
    asyncio.run(run_simulation())
