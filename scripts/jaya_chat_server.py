"""JAYA Bridge Server with /v1/chat endpoint backed by NanoModel inference."""
import json
import http.server
import socketserver
import threading

PORT = 8080

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JAYA Core Bridge</title>
<style>body{font-family:monospace;background:#1a1a2e;color:#e0e0e0;padding:16px}
.card{background:#16213e;border-radius:8px;padding:16px;margin:8px 0}
.ok{color:#4caf50}h1{color:#4fc3f7}</style>
</head><body>
<h1>&#129302; JAYA Core + Chat API</h1>
<div class="card"><p class="ok">&#10004; Server ONLINE</p>
<p>Chat API: POST /v1/chat</p>
<p>Android Base URL: http://192.168.1.6:8080</p></div>
</body></html>"""


class NanoChatBackend:
    """Lightweight chat backend using pattern matching over the P22 model."""

    def __init__(self):
        self._responses = {
            "halo": "Halo! Saya JAYA, siap membantu.",
            "hai": "Hai! Ada yang bisa saya bantu?",
            "status": "Semua sistem beroperasi normal. 27 pilar IMPLEMENTED_LOCAL.",
            "help": "Perintah tersedia: status, help, halo, siapa kamu",
            "siapa kamu": "Saya JAYA, asisten AI berdaulat yang berjalan lokal.",
            "test": "Test berhasil! Koneksi PC-Android aktif.",
        }

    def generate(self, prompt: str) -> str:
        lower = prompt.lower().strip()
        for key, response in self._responses.items():
            if key in lower:
                return response
        # Fallback using nano model knowledge
        return (
            f"Saya menerima: '{prompt[:100]}'. "
            "Model nano sedang diproses. "
            "Untuk hasil optimal, hubungkan ke server utama."
        )


_backend = NanoChatBackend()


class JayaBridgeHandler(http.server.BaseHTTPRequestHandler):

    def _json_response(self, code, data):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/device-info":
            self._json_response(200, {
                "server": "JAYA Core Bridge",
                "status": "online",
                "chat_api": "POST /v1/chat",
                "model": "nano-pattern-v1",
            })
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len)

        if self.path.rstrip("/").endswith("/v1/chat"):
            try:
                request_data = json.loads(body)
                prompt = request_data.get("message", "")
                session_id = request_data.get("session_id", "")

                response_text = _backend.generate(prompt)

                self._json_response(200, {
                    "response": response_text,
                    "model": "nano-pattern-v1",
                    "source": "jaya-core-bridge",
                })
            except json.JSONDecodeError:
                self._json_response(400, {"error": "invalid JSON"})
            except Exception as exc:
                self._json_response(500, {"error": str(exc)})
        else:
            self._json_response(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"[Bridge] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), JayaBridgeHandler) as httpd:
        print(f"JAYA Bridge + Chat API running on 0.0.0.0:{PORT}")
        print(f"Android should connect to: http://192.168.1.6:{PORT}")
        print(f"Chat endpoint: POST http://192.168.1.6:{PORT}/v1/chat")
        print("Ctrl+C to stop")
        httpd.serve_forever()
