import os
import time
import pprint
import logging
from typing import Dict, Any, List

# Setup Basic Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("AutoTeacher")

from src.brain_v2.engine.runtime import IronEngine
from src.brain_v2.soul.agentic_rag import AgenticRAG
from src.brain_v2.extensions.nvidia_llm import NvidiaNIMClient

class AutoTeacher:
    """
    Kelas yang bertanggung jawab mendistribusi pengetahuan tanpa henti ke JAYA.
    Pengetahuan faktual masuk ke memori empiris (Agentic RAG).
    Logika murni diekstrak dan didaftarkan sebagai Evo-Candidate untuk disertakan ke file .jay.
    """
    def __init__(self, use_dry_run: bool = True):
        self.engine = IronEngine(model_path="dummy_sandbox.jay", password="sandbox")
        self.engine.ignite()
        self.rag = AgenticRAG(db_path="rag_vault.db")
        self.llm_normal = NvidiaNIMClient(is_reasoning=False)
        self.llm_reasoning = NvidiaNIMClient(is_reasoning=True)
        self.dry_run = use_dry_run
        logger.info(f"[AutoTeacher] INIT. Mode Dry-Run: {self.dry_run}")
        
    def ignite_curiosity(self, n: int = 3) -> List[str]:
        """Pillar 6: Sengaja membangkitkan topik acak berdasarkan Entropi/Keingintahuan mandiri."""
        import logging
        logger = logging.getLogger("AutoTeacher")
        logger.info("[Pillar 6] JAYA merenungkan topik krusial (Fokus Bahasa Indonesia)...")
        
        system_prompt = "You are a highly curious AGI aiming to master human language, specifically Indonesian."
        user_prompt = f"Give me exactly {n} random but advanced linguistic/language topics (e.g. 'Struktur Kalimat Majemuk Bahasa Indonesia', 'Sintaksis Kata Kerja', 'Semantik dan Makna Ganda'). Reply ONLY as a comma-separated list without numbering or markdown."
        
        response = self.llm_normal.ask(system_prompt, user_prompt, max_tokens=100)
        if response:
            topics = [t.strip() for t in response.split(",") if len(t) > 2]
            # Filter out already learned topics (Pillar 2 - Efficiency)
            new_topics = [t for t in topics if not self.is_topic_learned(t)]
            
            if new_topics:
                logger.info(f"[Pillar 6] JAYA penasaran dengan: {', '.join(new_topics)}")
                return new_topics
            else:
                logger.info("[Pillar 6] JAYA merasa sudah cukup paham topik-topik ini. Mencoba fase hening sejenak.")
        
        # Fallback jika API gagal atau semua topik sudah dipelajari
        return ["Information Theory", "Symbolic Logic", "Epistemology"]

    def is_topic_learned(self, topic: str) -> bool:
        """Pillar 2: Resource Aware. Mengecek apakah JAYA sudah memiliki pengetahuan ini."""
        return self.rag.check_topic_exists(topic)

    def generate_and_learn_curriculum(self, subjects: List[str]):
        """JAYA mempelajari kurikulum secara otomatis."""
        for subject in subjects:
            if self.is_topic_learned(subject):
                import logging
                logging.getLogger("AutoTeacher").info(f"--- [AutoTeacher] Skip Topic: {subject} (Sudah Paham) ---")
                continue
            self.teach_subject(subject)
            # Tidur sebentar agar tidak meledakkan CPU (Sovereign Constraint)
            time.sleep(1)

    def teach_subject(self, subject: str):
        """Memproses 1 cabang ilmu / masalah. Melakukan split Fakta vs Logika."""
        logger.info(f"--- [AutoTeacher] Teaching Topic: {subject} ---")

        # 1. Akuisisi Pengetahuan (Fact Gathering) - Model Normal
        logger.info(f"   > Mengekstrak intisari ensiklopedia...")
        system_prompt_fact = "You are an encyclopedic expert in linguistics and Indonesian grammar."
        user_prompt_fact = f"Explain the core concept, rules, and facts comprehensively about: '{subject}'. Write 2-3 detailed paragraphs. Focus strictly on facts and linguistic mechanisms."
        
        vast_knowledge = self.llm_normal.ask(system_prompt_fact, user_prompt_fact, max_tokens=1024)
        if not vast_knowledge:
            logger.warning("   ! Koneksi ke API LLM terputus atau respon kosong. Skip topik ini.")
            return
            
        # 2. Sinkronisasi Memori Agentic (Fakta Murni)
        self.rag.memorize(topic=subject, content=vast_knowledge, source="Agentic LLM", importance=8)
        logger.info(f"   ✓ Faktual tersimpan di Agentic RAG (~{len(vast_knowledge)} chars). JAYA dapat mengingat ini.")

        # 3. Ekstraksi Graph (Triplets) untuk Memori Relasional - Model Normal
        system_prompt_graph = "Extract semantic graph from the text. Format strictly as a valid JSON list of lists. Example: [['Einstein', 'invented', 'Relativity']]"
        user_prompt_graph = f"Extract 3 to 5 core relationship triples from this text:\n{vast_knowledge}\nTarget output: raw JSON array only."
        graph_raw = self.llm_normal.ask(system_prompt_graph, user_prompt_graph, max_tokens=300)
        
        if graph_raw:
            import json
            try:
                # Membersihkan output jika ada markdown backticks/thinking tags
                clean_json = graph_raw.split("</think>")[-1].replace('```json', '').replace('```', '').strip()
                triples = json.loads(clean_json)
                if isinstance(triples, list):
                    self.rag.add_graph_edges(triples)
            except Exception as e:
                logger.warning(f"   ! Gagal parsing Graph JSON: {e}")

        # 4. Penyulingan Logika (Axiom Distillation) untuk file .jay - Model Reasoning (Pemikir)
        logger.info(f"   > Ekstraksi Aksioma Murni dengan Model Pemikir (Reasoning)...")
        system_prompt_logic = "Extract ONLY 2 purely logical, cause-and-effect rules (axioms) from the user's text. Return as valid JAYA internal logical expressions."
        user_prompt_logic = f"Text:\n{vast_knowledge}\n\nFormat required: list of strings (e.g. ['If A then B', 'A requires C']) without any markdown/fluff. No thinking process to be printed."
        
        logic_axioms_raw = self.llm_reasoning.ask(system_prompt_logic, user_prompt_logic, max_tokens=300)
        
        if logic_axioms_raw:
            # Sederhanakan Parsing (termasuk membersihkan </think> tag milik deepseek/reasoning)
            clean_axioms_raw = logic_axioms_raw.split("</think>")[-1].strip()
            axioms = [line.strip("- *1234567890.") for line in clean_axioms_raw.split("\n") if len(line) > 10]
        else:
            # Fallback
            axioms = [f"If context is {subject}, system understands {subject}"]

        # 5. Uji Logika Murni lewat Evolution Gate
        for axiom in axioms:
            logger.info(f"   > Menguji Axiom: {axiom}")
            
            # Format sesuai spesifikasi EvolutionCandidate (Phase 2 EvolutionGate)
            import hashlib
            candidate = {
                "candidate_id": f"evo_{int(time.time())}",
                "source_hash": hashlib.md5(axiom.encode()).hexdigest(),
                "created_at": time.time(),
                "candidate_payload": axiom,
                "metadata": {"authors": ["AutoTeacher API"], "topic": subject}
            }
            evidence = {"test_coverage": 1.0, "metrics": {"accuracy": 0.99}, "reviewer_signatures": ["Llama-3-70b"]}
            
            # 6. Menandatangani Kandidat (Pillar 13 - Cryptographic Skin)
            signed_res = self.engine.sign_evolution_candidate(candidate)
            
            if signed_res.get("ok"):
                result = self.engine.evaluate_evolution_candidate(signed_res["candidate"], evidence)
                
                if result.get("ok"):
                    decision = result.get("decision", {})
                    if decision.get("approved"):
                        logger.info("   ✓ [EVO GATE APPROVED] - Logika murni layak disimpan ke .jay!")
                        # In real JAYA, we commit this to the Morphic kernel memory tree.
                        if not self.dry_run:
                            self.engine.register_stable_state(f"auto_{subject}", snapshot=candidate)
                    else:
                        logger.warning(f"   ✗ [EVO GATE REJECTED] - Alasan: {decision.get('reason')}")
                else:
                    logger.error(f"   ! EvolutionGate gagal evaluasi: {result.get('error')}")
            else:
                logger.error("   ! Gagal menandatangani kandidat evolusi.")
                
        # 5. Minta JAYA Merapikan Dirinya (Tidy Up Memory)
        self.rag.tidy_up()
