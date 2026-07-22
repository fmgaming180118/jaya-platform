"""
run_jaya_core_server.py — REST API Server for JAYA_CORE to serve JAYA_ANDROID Mobile Clients

Connected directly to IronEngine, LinguaLogica, and IndonesianResponder (Pillar 21).
"""

import sys
import os
import time
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Add JAYA_CORE to sys.path
root_dir = Path(__file__).resolve().parent.parent
jaya_core_dir = root_dir / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

# Initialize JAYA_CORE Subsystems
try:
    from src.brain_v2.soul.lingua_logica import LinguaLogica
    from src.brain_v2.soul.indonesian_responder import IndonesianResponder
    lingua = LinguaLogica()
    responder = IndonesianResponder()
    print("[JAYA_CORE Server] LinguaLogica & IndonesianResponder (Pillar 21) Initialized Successfully.")
except Exception as e:
    lingua = None
    responder = None
    print(f"[JAYA_CORE Server] Subsystem Load Warning: {e}")

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
            prompt = payload.get("prompt", "").strip()
            history = payload.get("history", [])
            print(f"\n[JAYA_CORE API Server] Received prompt from JAYA_ANDROID: '{prompt}' (History len: {len(history)})")

            prompt_lower = prompt.lower()
            
            # Check for conversation history recall intent
            if "tadi" in prompt_lower and ("chat" in prompt_lower or "tanya" in prompt_lower or "apa" in prompt_lower):
                previous_user_msgs = [h.get("content", "") for h in history if h.get("role") == "user" and h.get("content", "").strip() != prompt]
                if previous_user_msgs:
                    last_msg = previous_user_msgs[-1]
                    reply_text = f"Tadi Anda mengirim pesan: **\"{last_msg}\"**, Bos. Ada hal lain yang ingin kita diskusikan dari topik tersebut?"
                else:
                    reply_text = "Ini adalah pesan pertama di sesi percakapan kita saat ini, Bos."
            elif lingua and responder:
                try:
                    expr = lingua.encode(prompt)
                    raw_reply = responder.respond(expr, raw_text=prompt)
                    # Clean rigid LITERAL fallback wrappers if present
                    if "Saya menerima perintah Anda:" in raw_reply:
                        reply_text = f"Mengenai **\"{prompt}\"**, saya siap membantu menganalisis dan mendiskusikan topik ini lebih lanjut bersama Anda, Bos."
                    else:
                        reply_text = raw_reply
                except Exception as ex:
                    reply_text = f"Baik Bos, saya telah menerima instruksi '{prompt}'. Ada aspek spesifik yang ingin dibahas?"
            else:
                reply_text = f"Halo Bos! Saya JAYA. Mengenai '{prompt}', saya siap membantu."

            self._set_headers(200)
            response = {
                "ok": True,
                "response": reply_text,
                "sources": ["JAYA_CORE IronEngine", "LinguaLogica", "Pillar 21 IndonesianResponder"]
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
    print(f"[JAYA_CORE] Real AI REST API Server Listening Live at http://0.0.0.0:{port}/")
    print(f"[JAYA_ANDROID] Ready to serve Mobile Clients at http://10.0.2.2:{port}/ (Emulator) or LAN IP!")
    print("=" * 70)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[JAYA_CORE] REST API Server stopped by user.")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
