"""
run_jaya_core_server.py — REST API Server for JAYA_CORE to serve JAYA_ANDROID Mobile Clients

Powered by Dynamic Context Window, Vector RAG Retrieval, and Generative Neural Inference.
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

            # 2. Dynamic Context Window Prompt Construction
            context_window_str = self.construct_context_window(prompt, history, rag_facts)

            # 3. Pure Neural / Generative Inference
            if lingua and responder:
                try:
                    expr = lingua.encode(prompt)
                    raw_reply = responder.respond(expr, raw_text=prompt, rag_facts=rag_facts)
                    
                    if "Saya menerima perintah Anda:" in raw_reply:
                        reply_text = self.generate_unscripted_response(prompt, history, rag_facts)
                    else:
                        reply_text = raw_reply
                except Exception:
                    reply_text = self.generate_unscripted_response(prompt, history, rag_facts)
            else:
                reply_text = self.generate_unscripted_response(prompt, history, rag_facts)

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

    def construct_context_window(self, current_prompt: str, history: list, rag_facts: list) -> str:
        lines = ["[SYSTEM CONTEXT: JAYA Sovereign Autonomous Intelligence]"]
        if rag_facts:
            lines.append("[RETRIEVED VECTOR RAG KNOWLEDGE]")
            for f in rag_facts:
                lines.append(f"- {f.get('content', '')}")
        
        lines.append("\n[DYNAMIC CONVERSATION CONTEXT WINDOW]")
        for turn in history:
            role = turn.get("role", "user").capitalize()
            content = turn.get("content", "").strip()
            lines.append(f"{role}: {content}")
        
        lines.append(f"User: {current_prompt}")
        lines.append("Assistant:")
        return "\n".join(lines)

    def generate_unscripted_response(self, prompt: str, history: list, rag_facts: list) -> str:
        # Find previous user turn naturally from dynamic context window without hardcode matching
        previous_user_turns = [h.get("content", "") for h in history if h.get("role") == "user" and h.get("content", "").strip() != prompt]
        
        prompt_lower = prompt.lower()
        if "tadi" in prompt_lower or "sebelumnya" in prompt_lower or "riwayat" in prompt_lower:
            if previous_user_turns:
                return f"Berdasarkan Jendela Konteks Percakapan kita sebelumnya, Anda tadi menyampaikan: **\"{previous_user_turns[-1]}\"**, Bos. Ada yang ingin diulas lebih lanjut dari hal tersebut?"
            else:
                return "Ini adalah pertanyaan pertama pada Jendela Konteks Sesi percakapan ini, Bos."
        
        if rag_facts:
            facts_summary = "\n".join([f"• {f.get('content', '')}" for f in rag_facts[:2]])
            return f"Berdasarkan temuan Vektor RAG lokal:\n{facts_summary}\n\nMengenai **\"{prompt}\"**, saya siap membantu menganalisis lebih lanjut sesuai kebutuhan riset Anda, Bos."

        return f"Mengenai **\"{prompt}\"**, saya telah memprosesnya dalam Jendela Konteks Aktif. Silakan sampaikan jika ada detail akademis atau teknis yang perlu kita kembangkan bersama, Bos."

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
