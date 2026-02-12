
import asyncio
import json
import logging
import uuid
import struct
from typing import Callable, Optional

from ..protection.crypto import CryptoSkin

# Configuration
TWIN_PORT = 7777
HEADER_SIZE = 4  # 4 bytes for payload length

logger = logging.getLogger("TwinSocket")

class TwinSocket:
    """
    Pillar 34: The Twin Protocol.
    
    Implements a P2P encrypted mesh network for Jaya instances.
    Uses asyncio TCP streams.
    
    Protocol:
    [Length (4 bytes)] [Encrypted Payload (N bytes)]
    """
    
    def __init__(self, hardware_id: bytes, crypto: CryptoSkin, password: str):
        self.host = "0.0.0.0"
        self.port = TWIN_PORT
        self.hardware_id = hardware_id
        self.crypto = crypto
        self.password = password
        
        # Determine Session Key (In real world, use Diffie-Hellman)
        # Here we assume Twins share the same "Soul Password"
        self.session_key, _ = self.crypto.derive_key(self.password, b"TWIN_LINK_V1", salt=b"JAYA_TWIN_SALT")
        
        self.server = None
        self.peers = {} # Address -> Writer
        self.on_message_callback = None
        self.is_running = False

    async def start_server(self):
        """Start listening for incoming Twins."""
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        self.is_running = True
        logger.info(f"[Twin] Listening on {self.host}:{self.port}")
        
        async with self.server:
            await self.server.serve_forever()

    async def connect_to_peer(self, ip: str):
        """Connect to another Jaya Twin."""
        try:
            reader, writer = await asyncio.open_connection(ip, self.port)
            logger.info(f"[Twin] Connected to {ip}")
            self.peers[ip] = writer
            
            # Start listening loop for this peer
            asyncio.create_task(self.read_from_peer(reader, ip))
            
            # Send Handshake
            handshake = {
                "type": "HANDSHAKE", 
                "hw_id": self.hardware_id.hex(),
                "node_id": str(uuid.uuid4())
            }
            await self.send_message(ip, handshake)
            
        except Exception as e:
            logger.error(f"[Twin] Failed to connect to {ip}: {e}")

    async def handle_client(self, reader, writer):
        """Handle incoming connection."""
        addr = writer.get_extra_info('peername')
        logger.info(f"[Twin] New connection from {addr}")
        self.peers[addr[0]] = writer
        await self.read_from_peer(reader, addr[0])

    async def read_from_peer(self, reader, addr):
        """Reading loop."""
        try:
            while True:
                # 1. Read Length Header
                header = await reader.read(HEADER_SIZE)
                if not header:
                    break
                
                msg_len = struct.unpack('!I', header)[0]
                
                # 2. Read Encrypted Payload
                encrypted_data = await reader.readexactly(msg_len)
                
                # 3. Decrypt
                # In robust implementation, handle decryption errors gracefully
                try:
                    # Strip simulation prefix if present (from crypto.py)
                    # Real decrypt
                    decrypted_data = self.crypto.decrypt_soul(encrypted_data, self.session_key)
                    payload = json.loads(decrypted_data.decode())
                    
                    if self.on_message_callback:
                        await self.on_message_callback(payload, addr)
                        
                except Exception as e:
                    logger.error(f"[Twin] Decryption Err from {addr}: {e}")
                    
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"[Twin] Connection lost with {addr}: {e}")
        finally:
            if addr in self.peers:
                del self.peers[addr]
            logger.info(f"[Twin] Disconnected: {addr}")

    async def send_message(self, target_ip: str, data: dict):
        """Encrypt and send message."""
        if target_ip not in self.peers:
            logger.warning(f"[Twin] Unknown peer: {target_ip}")
            return

        try:
            writer = self.peers[target_ip]
            json_str = json.dumps(data)
            
            # Encrypt
            encrypted = self.crypto.encrypt_soul(json_str.encode(), self.session_key)
            
            # Pack: [Len][Data]
            msg = struct.pack('!I', len(encrypted)) + encrypted
            
            writer.write(msg)
            await writer.drain()
            
        except Exception as e:
            logger.error(f"[Twin] Send Error to {target_ip}: {e}")

    def stop(self):
        self.is_running = False
        if self.server:
            self.server.close()
