"""Simple JAYA Bridge Server - serves status page accessible from Android device."""
import json
import http.server
import socketserver
import threading
import time

PORT = 8080

HTML_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JAYA Core Status</title>
<style>
body { font-family: monospace; background: #1a1a2e; color: #e0e0e0; padding: 16px; }
.card { background: #16213e; border-radius: 8px; padding: 16px; margin: 8px 0; }
.ok { color: #4caf50; } .warn { color: #ff9800; }
h1 { color: #4fc3f7; } h2 { color: #81c784; }
table { width: 100%; border-collapse: collapse; }
td { padding: 4px 8px; border-bottom: 1px solid #333; }
</style>
</head>
<body>
<h1>&#129302; JAYA Core Bridge</h1>
<div class="card"><h2>Connection</h2>
<p class="ok">&#10004; WiFi bridge ACTIVE</p>
<p>PC: 192.168.1.6 &lt;-&gt; Phone: 192.168.1.7</p>
</div>
<div class="card"><h2>Pillar Status (40 total)</h2>
<table>
<tr><td>VERIFIED</td><td class="ok">5</td></tr>
<tr><td>INTEGRATED</td><td class="ok">7</td></tr>
<tr><td>IMPLEMENTED_LOCAL</td><td class="warn">22</td></tr>
<tr><td>PROTOTYPE</td><td>6</td></tr>
<tr><td>NOT_IMPLEMENTED</td><td class="ok">0</td></tr>
<tr><td>PRODUCTION</td><td>0</td></tr>
</table>
</div>
<div class="card"><h2>Tahap Progress</h2>
<table>
<tr><td>Tahap 1-3 Pondasi+Keamanan</td><td class="ok">KOMPLET (INTEGRATED+)</td></tr>
<tr><td>Tahap 4 Rangka Mesin</td><td class="ok">KOMPLET (IL)</td></tr>
<tr><td>Tahap 5 Lantai Memori</td><td class="ok">KOMPLET (IL)</td></tr>
<tr><td>Tahap 6 Sistem Regulasi</td><td class="ok">KOMPLET (IL)</td></tr>
<tr><td>Tahap 7 Perawatan</td><td class="ok">KOMPLET (IL)</td></tr>
<tr><td>Tahap 8 Sensor & Lab</td><td class="warn">BERJALAN</td></tr>
<tr><td>Tahap 9 Ruang Kendali</td><td class="warn">BERJALAN</td></tr>
<tr><td>Tahap 10 Distribusi</td><td class="warn">BERJALAN</td></tr>
</table>
</div>
<div class="card"><h2>Your Device</h2>
<p id="device-info">Loading...</p>
</div>
<script>
fetch('/api/device-info')
  .then(r => r.json())
  .then(d => {
    document.getElementById('device-info').innerHTML =
      '<pre>' + JSON.stringify(d, null, 2) + '</pre>';
  })
  .catch(e => {
    document.getElementById('device-info').innerText =
      'Browser connected! Device info API not available.';
  });
document.getElementById('device-info').innerText =
  'Connected from: ' + window.location.hostname +
  '\\nUser Agent: ' + navigator.userAgent.slice(0, 80) + '...';
</script>
</body>
</html>"""


class JayaBridgeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/device-info":
            body = json.dumps({
                "server": "JAYA Core Bridge",
                "status": "online",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[Bridge] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), JayaBridgeHandler) as httpd:
        print(f"JAYA Bridge Server running on 0.0.0.0:{PORT}")
        print(f"Open http://192.168.1.6:{PORT} on your Android phone browser")
        print("Ctrl+C to stop")
        httpd.serve_forever()
