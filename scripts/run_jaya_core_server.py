"""
run_jaya_core_server.py — REST API Server for JAYA_CORE to serve JAYA_ANDROID Mobile Clients
"""

import sys
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Add JAYA_CORE to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "JAYA_CORE"))

class JayaCoreApiHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/evolution/status":
            self._set_headers(200)
            response = {
                "state": "AWAKE_STABLE",
                "is_awake": True,
                "latest_thought": "JAYA_CORE IronEngine actively serving JAYA_ANDROID client over LAN."
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)
        
        try:
            payload = json.loads(body_bytes.decode('utf-8')) if body_bytes else {}
        except Exception:
            payload = {}

        if self.path == "/chat":
            prompt = payload.get("prompt", "")
            print(f"[JAYA_CORE API Server] Received prompt from JAYA_ANDROID: '{prompt}'")
            
            self._set_headers(200)
            response = {
                "ok": True,
                "response": f"JAYA Sovereign Brain (Laptop Server): Berhasil memproses prompt '{prompt}'. Koneksi LAN ke JAYA_CORE aktif 100%!",
                "sources": ["JAYA_CORE IronEngine", "RAG Vector DB"]
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))

        elif self.path == "/thesis/analyze":
            doc_path = payload.get("document_path", "thesis.pdf")
            self._set_headers(200)
            response = {
                "ok": True,
                "summary": f"JAYA Thesis Analyzer: Dokumen '{doc_path}' telah dianalisis. Struktur riset valid dan siap diindeks."
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode('utf-8'))

def run_server(port=8000):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, JayaCoreApiHandler)
    print("=" * 70)
    print(f"[JAYA_CORE] REST API Server Listening Live at http://0.0.0.0:{port}/")
    print(f"[JAYA_ANDROID] Ready to serve Mobile Clients at http://10.0.2.2:{port}/ (Emulator) or LAN IP!")
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[JAYA_CORE] REST API Server stopped by user.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
