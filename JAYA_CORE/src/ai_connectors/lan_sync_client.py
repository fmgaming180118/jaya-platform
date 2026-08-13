"""
LAN Sync Client for Jaya AI
Handles discovery and synchronization with a peer device (e.g., laptop) over the local network.
Uses mDNS (zer) to discover services, then uses gRPC or a simple socket-based knowledge store (e.g., laptop) over LAN.
"""

import json
import logging
import socket
import struct
from typing import Any, Dict, List, Optional

try:
    import protobuf  # placeholder; we assume protobuf is available
except ImportError:
    protobuf = None

logger = logging.getLogger(__name__)

class LANSyncClient:
    def __init__(self, server_addr: Optional[str] = None, port: int = 50051):
        """
        Initialize LAN sync client.
        :param server_addr: IP address or hostname of the LAN peer (e.g., laptop). If None, attempt discovery via mDNS/broadcast.
        :param port: Port number for the LAN sync service.
        """
        self.server_addr = server_addr
        self.port = port
        self.socket = None
        self.connected = False
        if server_addr:
            self._connect()
        else:
            # In a real implementation, we would start discovery (e.g., zeroconf) here.
            # For simplicity, we leave it as None and rely on manual setting or broadcast.
            pass

    def _connect(self):
        """Establish a TCP connection to the LAN peer."""
        try:
            sock = socket.create_connection((self.server_addr, self.port), timeout=5)
            self.socket = sock
            self.connected = True
            logger.info(f"Connected to LAN peer at {self.server_addr}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to LAN peer: {e}")
            self.connected = False

    def discover_peers(self, timeout: float = 2.0) -> List[str]:
        """
        Discover LAN peers via UDP broadcast (simple implementation).
        Returns a list of IP addresses that respond.
        """
        # This is a simplified discovery; in production, use mDNS (zeroconf) or similar.
        found = []
        try:
            # Create a UDP socket
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.settimeout(timeout)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            message = b"JAYA_DISCOVERY"
            # Send to broadcast address (limited to local network)
            udp_sock.sendto(message, ('<broadcast>', self.port))
            while True:
                try:
                    data, addr = udp_sock.recvfrom(1024)
                    if data == b"JAYA_HERE":
                        found.append(addr[0])
                except socket.timeout:
                    break
            udp_sock.close()
        except Exception as e:
            logger.warning(f"Discovery failed: {e}")
        return found

    def query(self, user_intent: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Send a query to the LAN peer and get a response.
        :param user_intent: The user's intent.
        :param context: Optional context.
        :return: Response string from the peer, or None if failed.
        """
        if not self.connected:
            # Try to connect if we have a server address
            if self.server_addr:
                self._connect()
            else:
                # Attempt discovery
                peers = self.discover_peers()
                if peers:
                    self.server_addr = peers[0]
                    self._connect()
                else:
                    logger.warning("No LAN peer found for query.")
                    return None
        if not self.connected or not self.socket:
            return None
        try:
            # Prepare a simple request: length-prefixed JSON
            request = {
                "intent": user_intent,
                "context": context or {}
            }
            payload = json.dumps(request).encode('utf-8')
            header = struct.pack('>I', len(payload))
            self.socket.sendall(header + payload)
            # Read response
            header_data = self._recv_exact(4)
            if not header_data:
                return None
            msg_len = struct.unpack('>I', header_data)[0]
            data = self._recv_exact(msg_len)
            if not data:
                return None
            response = json.loads(data.decode('utf-8'))
            return response.get("response")
        except Exception as e:
            logger.error(f"Error during LAN query: {e}")
            self.connected = False
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            return None

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """Helper to receive exactly n bytes from socket."""
        buf = b''
        while len(buf) < n:
            try:
                chunk = self.socket.recv(n - len(buf))
                if not chunk:
                    return None
                buf += chunk
            except Exception:
                return None
        return buf

    def close(self):
        """Close the connection."""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            self.connected = False
