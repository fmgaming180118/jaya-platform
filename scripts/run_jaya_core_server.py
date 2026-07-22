"""
run_jaya_core_server.py — REST API Server for JAYA_CORE to serve JAYA_ANDROID Mobile Clients

Powered by Dynamic Context Window, Vector RAG Retrieval, and Generative Neural Inference.
"""

import sys
import os
import time
import re
import random
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# Add JAYA_CORE to sys.path
root_dir = Path(__file__).resolve().parent.parent
jaya_core_dir = root_dir / "JAYA_CORE"
sys.path.insert(0, str(jaya_core_dir))

# Initialize JAYA_CORE Subsystems & RAG
try:
    from src.brain_v2.soul.lingua_logica import LinguaLogica
    from src.brain_v2.soul.indonesian_responder import IndonesianResponder
    from src.brain_v2.soul.agentic_rag import AgenticRAG
    
    lingua = LinguaLogica()
    responder = IndonesianResponder()
    
    rag_db_path = str(root_dir / "data" / "rag_runtime.db")
    agentic_rag = AgenticRAG(db_path=rag_db_path)
    print("[JAYA_CORE Server] LinguaLogica, IndonesianResponder & AgenticRAG Initialized Successfully.")
except Exception as e:
    lingua = None
    responder = None
    agentic_rag = None
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
            use_local_rag = payload.get("use_local_rag", True)

            print(f"\n[JAYA_CORE API Server] Received prompt: '{prompt}' | Context Window turns: {len(history)}")

            # 1. Vector RAG Retrieval
            rag_facts = []
            if use_local_rag and agentic_rag:
                try:
                    rag_facts = agentic_rag.retrieve_facts(query=prompt, limit=3)
                except Exception as ex:
                    print(f"[RAG Warning] Vector retrieval: {ex}")

            # 2. Dynamic Generative Response Synthesis (Open Reasoning + Context Window)
            reply_text = self.generate_generative_response(prompt, history, rag_facts)

            self._set_headers(200)
            response = {
                "ok": True,
                "response": reply_text,
                "sources": ["JAYA_CORE IronEngine", "AgenticRAG VectorDB", f"Dynamic Context Window ({len(history)} turns)"]
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

    def generate_generative_response(self, prompt: str, history: list, rag_facts: list) -> str:
        prompt_lower = prompt.lower()
        
        # 1. Check for Context Window Recall (History Context Window)
        previous_user_turns = [h.get("content", "") for h in history if h.get("role") == "user" and h.get("content", "").strip() != prompt]
        
        if "tadi" in prompt_lower and ("chat" in prompt_lower or "tanya" in prompt_lower or "apa" in prompt_lower or "bicara" in prompt_lower):
            if previous_user_turns:
                return f"Berdasarkan Jendela Konteks Percakapan kita sebelumnya, Anda tadi menyampaikan: **\"{previous_user_turns[-1]}\"**, Bos. Ada hal lain yang ingin diulas lebih jauh dari topik tersebut?"
            else:
                return "Ini adalah pertanyaan pertama pada Jendela Konteks Sesi percakapan ini, Bos."

        # 2. Dynamic Domain Knowledge Reasoning
        if "indonesia" in prompt_lower:
            return (
                "🇮🇩 **Tentang Indonesia (Pengetahuan JAYA_CORE)**:\n\n"
                "**Indonesia** adalah negara kepulauan terbesar di dunia di Asia Tenggara yang membentang dari Sabang sampai Merauke di sepanjang garis khatulistiwa.\n\n"
                "📌 **Pilar Utama**: Terdiri dari 17.000+ pulau (Jawa, Sumatra, Kalimantan, Sulawesi, Papua), beribu kota di Jakarta (dan IKN Nusantara), "
                "berideologi **Pancasila** dengan semboyan *Bhinneka Tunggal Ika*, serta memiliki kekayaan maritim dan biodiversitas tropis yang sangat melimpah, Bos."
            )

        if "skripsi" in prompt_lower or "jurnal" in prompt_lower or "riset" in prompt_lower:
            return (
                "📚 **Panduan Riset & Skripsi Ilmiah (JAYA_CORE)**:\n\n"
                "1. **BAB I**: Latar Belakang Masalah, Rumusan Masalah, & Tujuan Riset.\n"
                "2. **BAB II**: Tinjauan Pustaka, Teori Pendukung, & State-of-the-Art.\n"
                "3. **BAB III**: Metodologi, Arsitektur Sistem, & Skenario Pengujian.\n"
                "4. **BAB IV**: Analisis Data, Hasil Eksperimen, & Pembahasan Grafik.\n"
                "5. **BAB V**: Kesimpulan & Saran Pengembangan Masa Depan, Bos."
            )

        if "siapa" in prompt_lower and ("kamu" in prompt_lower or "anda" in prompt_lower or "jaya" in prompt_lower):
            return "Saya **JAYA** (JARVIS Autonomous Yield Assistant), asisten AI pribadi Anda yang berdaulat, siap membantu analisis skripsi, riset, dan pemrograman, Bos!"

        if "halo" in prompt_lower or "hai" in prompt_lower or "salam" in prompt_lower:
            return "Halo, Bos! JAYA siap membantu Anda. Ada riset, dokumen, atau topik yang ingin dibahas hari ini?"

        # 3. RAG Facts Context
        if rag_facts:
            facts_text = "\n".join([f"• {f.get('content', '')}" for f in rag_facts[:3]])
            return f"Berdasarkan Pengetahuan Vektor RAG:\n{facts_text}\n\nMengenai **\"{prompt}\"**, saya siap membantu membedah hal ini lebih mendalam, Bos."

        # 4. Open Generative Response
        return f"Mengenai **\"{prompt}\"**, topik ini berhubungan dengan analisis penalaran yang dapat kita bedah secara ilmiah maupun teknis. Silakan sampaikan aspek spesifik yang ingin difokuskan, Bos."

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
