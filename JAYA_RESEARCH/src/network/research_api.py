import sys, os
# Reconfigure stdout/stderr to UTF-8 to prevent charmap UnicodeEncodeErrors on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config
"""
JAYA Research API Server (FastAPI)
The backbone of the Research UI.
"""
from contextlib import asynccontextmanager
from typing import List, Optional
import asyncio
import time
import sys
import os
import shutil
import tempfile
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Ensure both `src/` and project root are on sys.path so imports like `research.*` and `src.*` work
ROOT_DIR = Path(__file__).parent.parent.parent
SRC_DIR = ROOT_DIR / "src"
# insert src first for modules like `research.*`, then project root for `src.*` package imports
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from research.agent import ResearchAgent
from research.nvidia_rag_client import NVIDIARAGClient
from research.graph_rag import GraphRAGEngine
from research.meta_analysis import MetaAnalyst
from network.api_models import (
    ResearchRequest,
    ChatRequest,
    VideoIngestRequest,
    DebateRequest,
    IngestRequest,
    IngestResponse,
    RecursiveResearchRequest,
    RecursiveResearchResponse,
)
# VideoProcessor dimuat secara lazy (saat endpoint digunakan) karena membutuhkan cv2/ffmpeg opsional
VideoProcessor = None  # akan dimuat on-demand di endpoint /ingest/video
from research.workspace_manager import WorkspaceManager
from research.academic.journal_processor import JournalProcessor

from research.academic.tracker import ExperimentTracker
import traceback
from fastapi.responses import FileResponse
from evolution.twin import DigitalTwin

# Global Managers
workspace_manager = WorkspaceManager()
meta_analyst = None
active_sessions = {} # workspace_id -> {rag, graph}
# DigitalTwin may require external config/env — initialize safely
try:
    digital_twin = DigitalTwin()
except Exception as e:
    print(f"[API] DigitalTwin initialization failed: {e}")
    digital_twin = None

app = FastAPI(title="JAYA Research API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── LOOP STATE PERSISTENCE HELPERS ─────────────────
def _get_settings_db_path() -> Path:
    """Returns path to agentic_jarvis.db for settings persistence."""
    return Path(__file__).resolve().parent.parent.parent / "data" / "agentic_jarvis.db"

def _ensure_settings_table():
    """Create jaya_settings table if not exists."""
    try:
        import sqlite3 as _sq
        db = _get_settings_db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = _sq.connect(str(db))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS jaya_settings "
            "(key TEXT PRIMARY KEY, value TEXT, updated_at REAL)"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SETTINGS] Could not create settings table: {e}")

def _save_loop_state(running: bool):
    """Persist autonomous loop enabled/disabled to SQLite."""
    try:
        import sqlite3 as _sq
        conn = _sq.connect(str(_get_settings_db_path()))
        conn.execute(
            "INSERT OR REPLACE INTO jaya_settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("autonomous_loop_enabled", "1" if running else "0", time.time())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SETTINGS] Could not save loop state: {e}")

def _read_loop_state() -> bool:
    """Read persisted autonomous loop state from SQLite."""
    try:
        import sqlite3 as _sq
        db = _get_settings_db_path()
        if not db.exists():
            return False
        conn = _sq.connect(str(db))
        row = conn.execute(
            "SELECT value FROM jaya_settings WHERE key = 'autonomous_loop_enabled'"
        ).fetchone()
        conn.close()
        return row is not None and row[0] == "1"
    except Exception:
        return False

_ensure_settings_table()

@app.on_event("startup")
async def startup_event():
    global _is_autonomous_loop_running, _auto_loop_task
    print("[API] Starting JAYA Research Backend...")
    if digital_twin is not None:
        try:
            import threading
            def run_twin():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(digital_twin.start_loop())
            t = threading.Thread(target=run_twin, daemon=True)
            t.start()
            print("[API] Started DigitalTwin loop in background thread.")
        except Exception as e:
            print(f"[API] Failed to start DigitalTwin loop: {e}")

    # ⭐ Auto-restore autonomous loop state from SQLite
    was_running = _read_loop_state()
    if was_running:
        _is_autonomous_loop_running = True
        _auto_loop_task = asyncio.create_task(_continuous_autonomous_research_worker())
        print("[API] ⭐ Autonomous Research Loop auto-restored from persisted state!")
    else:
        print("[API] Autonomous Research Loop not running (last saved state: stopped).")

@app.on_event("shutdown")
async def shutdown_event():
    print("[API] Shutting down...")
    if digital_twin is not None:
        try:
            digital_twin.stop()
        except Exception as e:
            print(f"[API] Error stopping DigitalTwin: {e}")

# CORS for Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session State (In-Memory for MVP - ideal: Redis)
# Map workspace_id -> {rag_client, graph_engine}
# active_sessions is already declared above

def get_engines(workspace_id: str = "default"):
    """
    Lazy load engines for a specific workspace.
    Returns (rag_client, graph_engine)
    """
    if workspace_id not in active_sessions:
        print(f"[API] Loading engines for workspace: {workspace_id}")
        paths = workspace_manager.get_or_create_paths(workspace_id)
        
        # Initialize engines with specific paths
        rag = NVIDIARAGClient(
            vector_store_path=paths['vector_store'],
            workspace_id=workspace_id,
        )
        graph = GraphRAGEngine(storage_path=paths['knowledge_graph'])
        
        active_sessions[workspace_id] = {
            "rag": rag,
            "graph": graph
        }
    
    return active_sessions[workspace_id]["rag"], active_sessions[workspace_id]["graph"]


def _recursive_search(rag_client, query: str, depth: int, max_sources_per_level: int, workspace_id: str):
    """Perform bounded recursive retrieval for Phase A."""
    seen_sources = set()
    collected: list[dict] = []
    frontier = [query]

    for current_depth in range(depth):
        next_frontier = []
        for item in frontier:
            results = rag_client.search(item, top_k=max_sources_per_level, workspace_id=workspace_id)
            for result in results:
                document = result.get("document", {})
                source = document.get("file_name") or document.get("source") or document.get("path") or "unknown"
                if source in seen_sources:
                    continue
                seen_sources.add(source)
                collected.append(result)
                snippet = result.get("snippet") or result.get("content") or ""
                if snippet:
                    next_frontier.append(snippet[:300])
        frontier = next_frontier[:max_sources_per_level]
        if not frontier:
            return collected, current_depth + 1

    return collected, depth

# Pre-load default (safe): try but don't crash if model config missing
try:
    get_engines("default")
except Exception as e:
    print(f"[API] Warning: failed to pre-load engines: {e}")
    # Engines will be lazy-loaded on first request

@app.get("/")
def health_check():
    return {"status": "online", "service": "JAYA Research API"}


@app.get("/workspaces")
async def list_workspaces():
    """List all research workspaces."""
    try:
        from research.workspace_manager import WorkspaceManager
        wm = WorkspaceManager()
        workspaces = wm.list_workspaces()
        return {"workspaces": workspaces}
    except Exception as e:
        return {"workspaces": [{"id": "default", "name": "Default Workspace"}]}


@app.post("/workspaces/create")
async def create_workspace(name: str, description: str = ""):
    """Create a new research workspace."""
    try:
        from research.workspace_manager import WorkspaceManager
        wm = WorkspaceManager()
        res = wm.create_workspace(name=name, description=description)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    """Delete a research workspace."""
    try:
        from research.workspace_manager import WorkspaceManager
        wm = WorkspaceManager()
        res = wm.delete_workspace(workspace_id)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest", response_model=IngestResponse)
async def ingest_text(request: IngestRequest):
    """Ingest raw text into the workspace RAG store."""
    try:
        rag_client, _ = get_engines(request.workspace_id)
        result = rag_client.ingest_text(request.text, metadata=request.metadata)
        return IngestResponse(
            status=result.get("status", "success"),
            chunks_added=int(result.get("chunks_added", 0)),
            workspace_id=result.get("workspace_id", request.workspace_id),
            message=result.get("message"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest text: {e}")


@app.post("/research/recursive", response_model=RecursiveResearchResponse)
async def recursive_research(request: RecursiveResearchRequest):
    """Bounded recursive retrieval + synthesis for academic research queries."""
    try:
        rag_client, graph_engine = get_engines(request.workspace_id)
        results, depth_reached = _recursive_search(
            rag_client=rag_client,
            query=request.query,
            depth=max(1, request.depth),
            max_sources_per_level=max(1, request.max_sources_per_level),
            workspace_id=request.workspace_id,
        )

        vector_context = "\n\n".join(
            f"[{idx}] {item.get('snippet') or item.get('content', '')}" for idx, item in enumerate(results, 1)
        )
        graph_context = graph_engine.get_context(request.query) if graph_engine else ""
        synthesis_parts = []
        if vector_context:
            synthesis_parts.append("[Vector Context]\n" + vector_context)
        if graph_context:
            synthesis_parts.append("[Graph Context]\n" + graph_context)

        synthesis = "\n\n".join(synthesis_parts) if synthesis_parts else "No relevant context found."

        return RecursiveResearchResponse(
            query=request.query,
            synthesis=synthesis,
            sources=results,
            depth_reached=depth_reached,
            workspace_id=request.workspace_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to run recursive research: {e}")

# --- Workspace Management ---
@app.get("/workspaces")
def list_workspaces():
    return workspace_manager.list_workspaces()

@app.post("/workspaces/create")
def create_workspace(name: str):
    return workspace_manager.create_workspace(name)

@app.post("/research/autonomous")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start autonomous research in background"""
    workspace_id = request.workspace_id
    rag_client, graph_engine = get_engines(workspace_id)
    
    def run_agent(topic, focus):
        agent = ResearchAgent(topic=topic, focus_areas=focus)
        report = agent.run(human_in_loop=False) # Auto mode
        
        # Ingest into Graph
        print(f"[API] Ingesting report into Knowledge Graph ({workspace_id})...")
        graph_engine.ingest_document(report, f"Research: {topic}")
        
        # Ingest into Vector Store (Optional but good)
        # rag_client.ingest_text(report) 
        
        print(f"[API] Research completed for: {topic}")
        
    background_tasks.add_task(run_agent, request.topic, request.focus_areas)
    return {"message": "Research started", "topic": request.topic, "workspace": workspace_id}

@app.post("/academic/defense")
async def generate_defense_questions(topic: str, abstract: str):
    """Generates Thesis Defense Q&A"""
    # Lazy import because reviewer module may have heavy deps or cause import errors
    from research.academic.reviewer import ReviewerAgent
    reviewer = ReviewerAgent()
    questions = reviewer.generate_defense_questions(topic, abstract)
    return {"topic": topic, "questions": questions}

@app.post("/academic/gaps")
async def find_research_gaps(topic: str):
    """Identifies Research Gaps using Citation Network"""
    from research.academic.gap_finder import GapFinder
    finder = GapFinder()
    finder.build_network(topic)
    report = finder.analyze_gaps()
    return {"topic": topic, "report": report}

@app.post("/academic/slides")
async def generate_slides(topic: str, content: str = "Automated generated content"):
    """Generates Marp Slides for a topic"""
    from research.academic.presenter import SlideDeckGenerator
    presenter = SlideDeckGenerator()
    slides_md = presenter.generate_slides(topic, content)
    return {"topic": topic, "slides": slides_md}


# =============================================================================
# PDF INGESTION ENDPOINT - Multimodal PDF Processing with JAYA Integration
# =============================================================================

class PDFIngestRequest(BaseModel):
    workspace_id: str = "default"
    extract_images: bool = True
    extract_tables: bool = True
    analyze_with_llm: bool = True
    store_in_rag: bool = True
    store_in_graph: bool = True
    store_in_citation_graph: bool = True


@app.post("/documents/ingest-pdf")
async def ingest_pdf_document(
    background_tasks: BackgroundTasks,
    workspace_id: str = "default",
    extract_images: bool = True,
    extract_tables: bool = True,
    analyze_with_llm: bool = True,
    store_in_rag: bool = True,
    store_in_graph: bool = True,
    store_in_citation_graph: bool = True,
    file: UploadFile = File(...)
):
    """
    Ingest a PDF document with multimodal extraction (text, images, tables).
    
    Features:
    - Text extraction with pdfplumber (better than PyPDF)
    - Image extraction with PyMuPDF
    - Table extraction and conversion to Markdown
    - LLM analysis for structured summary
    - Integration with JAYA's RAG, Knowledge Graph, and Citation Graph
    - Automatic workspace isolation
    
    Returns:
        - Document metadata
        - Extracted content summary
        - Storage locations
    """
    # Validate file
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Get workspace paths
    paths = workspace_manager.get_paths(workspace_id)
    workspace_root = Path(paths['vector_store']).parent  # Get workspace root from vector_store path
    
    # Create documents directory in workspace
    docs_dir = workspace_root / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    
    # Save uploaded PDF
    safe_filename = Path(file.filename).name
    # prevent path traversal
    pdf_path = docs_dir / safe_filename
    
    try:
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save PDF: {e}")
    
    # Process in background
    def process_pdf():
        try:
            _process_pdf_background(
                pdf_path=pdf_path,
                workspace_id=workspace_id,
                paths=paths,
                extract_images=extract_images,
                extract_tables=extract_tables,
                analyze_with_llm=analyze_with_llm,
                store_in_rag=store_in_rag,
                store_in_graph=store_in_graph,
                store_in_citation_graph=store_in_citation_graph,
            )
        except Exception as e:
            print(f"[API] PDF processing error: {e}")
            import traceback
            traceback.print_exc()
    
    background_tasks.add_task(process_pdf)
    
    return {
        "status": "processing",
        "message": "PDF upload successful, processing started in background",
        "workspace_id": workspace_id,
        "filename": safe_filename,
        "pdf_path": str(pdf_path.relative_to(ROOT_DIR)),
    }


def _process_pdf_background(
    pdf_path: Path,
    workspace_id: str,
    paths: dict,
    extract_images: bool,
    extract_tables: bool,
    analyze_with_llm: bool,
    store_in_rag: bool,
    store_in_graph: bool,
    store_in_citation_graph: bool,
):
    """Background task to process PDF with full multimodal extraction"""
    import pdfplumber
    import fitz  # PyMuPDF
    import time
    from teacher import Teacher
    from research.academic.journal_processor import JournalProcessor, PaperCache
    from research.academic.citation_graph import get_citation_graph
    
    print(f"[PDF Ingest] Starting processing: {pdf_path.name}")
    start_time = time.time()
    
    # Compute workspace_root from paths
    workspace_root = Path(paths['vector_store']).parent
    
    # Initialize components
    teacher = Teacher(model_type="reasoning")
    journal_processor = JournalProcessor()
    paper_cache = PaperCache()
    citation_graph = get_citation_graph()
    
    # Create output folder for this document
    doc_folder_name = pdf_path.stem.replace(' ', '_').replace('(', '').replace(')', '')
    doc_folder = workspace_root / "processed_docs" / doc_folder_name
    doc_folder.mkdir(parents=True, exist_ok=True)
    
    # Copy PDF to processed folder
    pdf_copy = doc_folder / pdf_path.name
    shutil.copy2(pdf_path, pdf_copy)
    
    # ============================================================
    # 1. EXTRACT TEXT & TABLES with pdfplumber
    # ============================================================
    print(f"[PDF Ingest] Extracting text and tables...")
    pdfplumber_data = {
        "pages": [],
        "tables": [],
        "full_text": ""
    }
    
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            
            tables = page.extract_tables() or []
            page_tables = []
            for table_idx, table in enumerate(tables):
                if table and any(cell for row in table for cell in row if cell):
                    page_tables.append({
                        "page": i,
                        "table_index": table_idx,
                        "data": table
                    })
                    pdfplumber_data["tables"].append({
                        "page": i,
                        "table_index": table_idx,
                        "data": table
                    })
            
            pdfplumber_data["pages"].append({
                "page": i,
                "text": text,
                "tables": page_tables
            })
            pdfplumber_data["full_text"] += f"\n--- PAGE {i} ---\n" + text + "\n\n"
    
    # Save full text
    text_file = doc_folder / "full_text.txt"
    with open(text_file, "w", encoding="utf-8") as f:
        f.write(pdfplumber_data["full_text"])
    
    # ============================================================
    # 2. EXTRACT IMAGES with PyMuPDF
    # ============================================================
    images = []
    if extract_images:
        print(f"[PDF Ingest] Extracting images...")
        images_folder = doc_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)
        
        doc_fitz = fitz.open(str(pdf_path))
        for page_num in range(len(doc_fitz)):
            page = doc_fitz[page_num]
            image_list = page.get_images(full=True)
            
            for img_idx, img in enumerate(image_list):
                xref = img[0]
                base_image = doc_fitz.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                img_filename = f"page_{page_num+1}_img_{img_idx+1}.{image_ext}"
                img_path = images_folder / img_filename
                
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                
                images.append({
                    "page": page_num + 1,
                    "index": img_idx + 1,
                    "filename": img_filename,
                    "path": str(img_path.relative_to(ROOT_DIR)),
                    "width": base_image.get("width", 0),
                    "height": base_image.get("height", 0),
                    "ext": image_ext
                })
        doc_fitz.close()
        print(f"[PDF Ingest] Extracted {len(images)} images")
    
    # ============================================================
    # 3. EXTRACT REFERENCES SECTION
    # ============================================================
    import re
    def extract_references_section(full_text: str) -> str:
        ref_patterns = [
            r'\n\s*references\s*\n',
            r'\n\s*bibliography\s*\n',
            r'\n\s*reference list\s*\n',
            r'\n\s*literature cited\s*\n',
            r'\n\s*works cited\s*\n',
            r'\n\s*daftar pustaka\s*\n',
            r'\n\s*referensi\s*\n',
        ]
        text_lower = full_text.lower()
        for pattern in ref_patterns:
            match = re.search(pattern, text_lower)
            if match:
                return full_text[match.start():]
        return full_text[-15000:]
    
    references_text = extract_references_section(pdfplumber_data["full_text"])
    ref_file = doc_folder / "references.txt"
    with open(ref_file, "w", encoding="utf-8") as f:
        f.write(references_text)
    
    # ============================================================
    # 4. LLM ANALYSIS
    # ============================================================
    llm_analysis = {}
    if analyze_with_llm:
        print(f"[PDF Ingest] Analyzing with LLM...")
        analysis_text = pdfplumber_data["full_text"][:50000]
        
        prompt = f"""
Anda adalah Research Analyst. Analisis dokumen PDF berikut dan ekstrak informasi terstruktur.

Nama File: {pdf_path.name}

Konten Dokumen (ekstrak):
{analysis_text}
...

Tugas:
1. Ekstrak metadata: Judul, Penulis, Tahun, Abstrak, Kata Kunci
2. Identifikasi struktur dokumen (Bab/Section)
3. Ekstrak: Masalah, Tujuan, Metodologi, Hasil Utama, Kesimpulan, Saran
4. Identifikasi tabel dan gambar penting beserta caption/deskripsi
5. Ekstrak referensi utama (top 15 referensi paling relevan)
6. Buat ringkasan eksekutif (3-4 paragraf)

Format output sebagai JSON dengan keys:
- metadata: {{title, authors, year, abstract, keywords}}
- structure: {{sections: []}}
- problem_statement: ""
- objectives: []
- methodology: ""
- key_results: []
- conclusions: []
- suggestions: []
- tables_summary: [{{page, description, caption}}]
- figures_summary: [{{page, description, caption}}]
- references: [{{title, authors, year, source}}]
- executive_summary: ""
"""
        
        try:
            response = teacher.ask(
                prompt,
                system_instruction="Anda adalah Research Analyst. Output HANYA JSON valid, tanpa markdown atau penjelasan tambahan."
            )
            
            response = response.strip()
            response = re.sub(r'^```json\s*', '', response)
            response = re.sub(r'^```\s*', '', response)
            response = re.sub(r'\s*```$', '', response)
            
            llm_analysis = json.loads(response)
        except Exception as e:
            print(f"[PDF Ingest] LLM Analysis error: {e}")
            llm_analysis = {}
    
    # Save LLM analysis
    analysis_file = doc_folder / "analysis.json"
    with open(analysis_file, "w", encoding="utf-8") as f:
        json.dump(llm_analysis, f, ensure_ascii=False, indent=2)
    
    # ============================================================
    # 5. CREATE MARKDOWN DOCUMENT
    # ============================================================
    def create_markdown(pdfplumber_data, images, llm_analysis, references_text):
        metadata = llm_analysis.get("metadata", {})
        structure = llm_analysis.get("structure", {})
        problem = llm_analysis.get("problem_statement", "")
        objectives = llm_analysis.get("objectives", [])
        methodology = llm_analysis.get("methodology", "")
        key_results = llm_analysis.get("key_results", [])
        conclusions = llm_analysis.get("conclusions", [])
        suggestions = llm_analysis.get("suggestions", [])
        tables_summary = llm_analysis.get("tables_summary", [])
        figures_summary = llm_analysis.get("figures_summary", [])
        references = llm_analysis.get("references", [])
        exec_summary = llm_analysis.get("executive_summary", "")
        
        md_lines = []
        title = metadata.get('title', pdf_path.name)
        md_lines.append(f"# {title}")
        md_lines.append("")
        
        # Metadata
        md_lines.append("## 📋 Metadata")
        md_lines.append("")
        md_lines.append(f"- **File Asli**: `{pdf_path.name}`")
        md_lines.append(f"- **Judul**: {metadata.get('title', 'Tidak diketahui')}")
        md_lines.append(f"- **Penulis**: {', '.join(metadata.get('authors', ['Tidak diketahui']))}")
        md_lines.append(f"- **Tahun**: {metadata.get('year', 'Tidak diketahui')}")
        md_lines.append(f"- **Kata Kunci**: {', '.join(metadata.get('keywords', []))}")
        md_lines.append("")
        
        if exec_summary:
            md_lines.append("## 🎯 Ringkasan Eksekutif")
            md_lines.append("")
            md_lines.append(exec_summary)
            md_lines.append("")
        
        if problem:
            md_lines.append("## ❓ Rumusan Masalah")
            md_lines.append("")
            md_lines.append(problem)
            md_lines.append("")
        
        if objectives:
            md_lines.append("## 🎯 Tujuan")
            md_lines.append("")
            for i, obj in enumerate(objectives, 1):
                md_lines.append(f"{i}. {obj}")
            md_lines.append("")
        
        if methodology:
            md_lines.append("## 🔬 Metodologi")
            md_lines.append("")
            md_lines.append(methodology)
            md_lines.append("")
        
        if key_results:
            md_lines.append("## 📈 Hasil Utama")
            md_lines.append("")
            for i, result in enumerate(key_results, 1):
                md_lines.append(f"{i}. {result}")
            md_lines.append("")
        
        if conclusions:
            md_lines.append("## ✅ Kesimpulan")
            md_lines.append("")
            for i, conc in enumerate(conclusions, 1):
                md_lines.append(f"{i}. {conc}")
            md_lines.append("")
        
        if suggestions:
            md_lines.append("## 💡 Saran")
            md_lines.append("")
            for i, sug in enumerate(suggestions, 1):
                md_lines.append(f"{i}. {sug}")
            md_lines.append("")
        
        if structure.get('sections'):
            md_lines.append("## 📑 Struktur Dokumen")
            md_lines.append("")
            for section in structure['sections']:
                md_lines.append(f"- {section}")
            md_lines.append("")
        
        # Tables
        if tables_summary:
            md_lines.append("## 📊 Tabel (Summary LLM)")
            md_lines.append("")
            for table in tables_summary:
                md_lines.append(f"### Tabel Halaman {table.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {table.get('description', '')}")
                if table.get('caption'):
                    md_lines.append(f"**Caption**: {table['caption']}")
                md_lines.append("")
        
        if pdfplumber_data.get("tables"):
            md_lines.append("## 📋 Data Tabel Lengkap (Ekstraksi Otomatis)")
            md_lines.append("")
            for table in pdfplumber_data["tables"]:
                md_lines.append(f"### Tabel Halaman {table['page']} (Indeks {table['table_index']})")
                md_lines.append("")
                if table['data']:
                    md_lines.append("| " + " | ".join(str(cell or "") for cell in table['data'][0]) + " |")
                    md_lines.append("| " + " | ".join(["---"] * len(table['data'][0])) + " |")
                    for row in table['data'][1:]:
                        md_lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")
                md_lines.append("")
        
        # Figures
        if figures_summary:
            md_lines.append("## 🖼️ Gambar/Figur (Summary LLM)")
            md_lines.append("")
            for fig in figures_summary:
                md_lines.append(f"### Gambar Halaman {fig.get('page', '?')}")
                md_lines.append(f"**Deskripsi**: {fig.get('description', '')}")
                if fig.get('caption'):
                    md_lines.append(f"**Caption**: {fig['caption']}")
                md_lines.append("")
        
        if images:
            md_lines.append("## 🖼️ Gambar yang Diekstrak")
            md_lines.append("")
            for img in images:
                md_lines.append(f"### Gambar Halaman {img['page']} #{img['index']}")
                md_lines.append(f"![Gambar]({img['path']})")
                md_lines.append(f"*Ukuran: {img['width']}x{img['height']} px*")
                md_lines.append("")
        
        # References
        if references:
            md_lines.append("## 📚 Referensi Utama")
            md_lines.append("")
            for i, ref in enumerate(references, 1):
                md_lines.append(f"{i}. **{ref.get('title', 'Judul tidak tersedia')}**")
                if ref.get('authors'):
                    md_lines.append(f"   - Penulis: {', '.join(ref['authors'])}")
                if ref.get('year'):
                    md_lines.append(f"   - Tahun: {ref['year']}")
                if ref.get('source'):
                    md_lines.append(f"   - Sumber: {ref['source']}")
                md_lines.append("")
        
        if references_text:
            md_lines.append("## 📖 Bagian Referensi Lengkap (Ekstraksi)")
            md_lines.append("")
            md_lines.append("```")
            md_lines.append(references_text[:5000])
            if len(references_text) > 5000:
                md_lines.append("... (dipotong)")
            md_lines.append("```")
            md_lines.append("")
        
        # Full text (truncated)
        md_lines.append("## 📝 Teks Lengkap (Ekstraksi pdfplumber)")
        md_lines.append("")
        full_text = pdfplumber_data.get("full_text", "")
        md_lines.append("```")
        md_lines.append(full_text[:10000])
        if len(full_text) > 10000:
            md_lines.append("... (dipotong, lihat file teks terpisah)")
        md_lines.append("```")
        
        return "\n".join(md_lines)
    
    markdown_content = create_markdown(pdfplumber_data, images, llm_analysis, references_text)
    md_file = doc_folder / f"{doc_folder_name}.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    # ============================================================
    # 6. STORE IN JAYA SYSTEMS
    # ============================================================
    
    # 6a. Store in RAG (Vector Store)
    if store_in_rag:
        try:
            print(f"[PDF Ingest] Storing in RAG...")
            rag_client, _ = get_engines(workspace_id)
            # Ingest the markdown content
            rag_client.ingest_documents([str(md_file)])
            print(f"[PDF Ingest] Stored in RAG")
        except Exception as e:
            print(f"[PDF Ingest] RAG storage error: {e}")
    
    # 6b. Store in Knowledge Graph
    if store_in_graph:
        try:
            print(f"[PDF Ingest] Storing in Knowledge Graph...")
            _, graph_engine = get_engines(workspace_id)
            # Create a document node with metadata
            doc_metadata = {
                "title": llm_analysis.get("metadata", {}).get("title", pdf_path.name),
                "source": "pdf_ingest",
                "file_path": str(pdf_copy.relative_to(ROOT_DIR)),
                "markdown_path": str(md_file.relative_to(ROOT_DIR)),
                "pages": len(pdfplumber_data["pages"]),
                "tables_count": len(pdfplumber_data["tables"]),
                "images_count": len(images),
                "workspace_id": workspace_id,
                "ingested_at": time.time(),
            }
            graph_engine.ingest_document(markdown_content, f"Document: {pdf_path.name}")
            print(f"[PDF Ingest] Stored in Knowledge Graph")
        except Exception as e:
            print(f"[PDF Ingest] Graph storage error: {e}")
    
    # 6c. Store in Citation Graph (if academic paper)
    if store_in_citation_graph and llm_analysis.get("references"):
        try:
            print(f"[PDF Ingest] Storing in Citation Graph...")
            paper_meta = {
                "title": llm_analysis.get("metadata", {}).get("title", pdf_path.name),
                "source": "pdf_ingest",
                "year": str(llm_analysis.get("metadata", {}).get("year", "")),
                "authors": llm_analysis.get("metadata", {}).get("authors", []),
                "abstract": llm_analysis.get("metadata", {}).get("abstract", ""),
                "pdf_link": "",
                "local_path": str(pdf_copy),
                "language": "id" if any(c in pdf_path.name.lower() for c in ['indonesia', 'ind']) else "en",
                "rank_score": 0.5,
                "insight_excerpt": llm_analysis.get("executive_summary", "")[:500],
                "fetched_at": time.time(),
            }
            references = llm_analysis.get("references", [])
            citation_graph.add_paper(paper_meta, references)
            print(f"[PDF Ingest] Stored in Citation Graph with {len(references)} references")
        except Exception as e:
            print(f"[PDF Ingest] Citation graph storage error: {e}")
    
    # 6d. Store in Paper Cache
    try:
        paper_meta = {
            "title": llm_analysis.get("metadata", {}).get("title", pdf_path.name),
            "source": "pdf_ingest",
            "published": str(llm_analysis.get("metadata", {}).get("year", "")),
            "authors": llm_analysis.get("metadata", {}).get("authors", []),
            "summary": llm_analysis.get("executive_summary", ""),
            "pdf_link": "",
            "landing_page_url": "",
            "language": "id" if any(c in pdf_path.name.lower() for c in ['ind']) else "en",
        }
        insight = llm_analysis.get("executive_summary", "")
        paper_cache.put(paper_meta, insight, str(pdf_copy), llm_analysis.get("references", []))
        print(f"[PDF Ingest] Stored in Paper Cache")
    except Exception as e:
        print(f"[PDF Ingest] Paper cache error: {e}")
    
    # ============================================================
    # 7. SAVE SUMMARY
    # ============================================================
    summary = {
        "pdf_name": pdf_path.name,
        "folder_name": doc_folder_name,
        "pages": len(pdfplumber_data["pages"]),
        "tables_count": len(pdfplumber_data["tables"]),
        "images_count": len(images),
        "has_llm_analysis": bool(llm_analysis),
        "markdown_file": str(md_file.relative_to(ROOT_DIR)),
        "pdf_file": str(pdf_copy.relative_to(ROOT_DIR)),
        "text_file": str(text_file.relative_to(ROOT_DIR)),
        "analysis_file": str(analysis_file.relative_to(ROOT_DIR)),
        "references_file": str(ref_file.relative_to(ROOT_DIR)),
        "images_folder": "images/",
        "stored_in": {
            "rag": store_in_rag,
            "graph": store_in_graph,
            "citation_graph": store_in_citation_graph,
        },
        "processing_time_sec": round(time.time() - start_time, 2),
    }
    
    summary_file = doc_folder / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"[PDF Ingest] ✅ Completed in {summary['processing_time_sec']}s: {pdf_path.name}")


# =============================================================================
# LIST PROCESSED DOCUMENTS
# =============================================================================

@app.get("/documents/processed")
def list_processed_documents(workspace_id: str = "default"):
    """List all processed documents in a workspace"""
    paths = workspace_manager.get_paths(workspace_id)
    workspace_root = Path(paths['vector_store']).parent
    processed_dir = workspace_root / "processed_docs"
    
    if not processed_dir.exists():
        return {"documents": []}
    
    documents = []
    for doc_folder in processed_dir.iterdir():
        if doc_folder.is_dir():
            summary_file = doc_folder / "summary.json"
            if summary_file.exists():
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                documents.append(summary)
    
    # Sort by processing time (newest first)
    documents.sort(key=lambda x: x.get("processing_time_sec", 0), reverse=True)
    
    return {"documents": documents}


@app.get("/documents/processed/{doc_folder_name}")
def get_processed_document(workspace_id: str, doc_folder_name: str):
    """Get details of a processed document"""
    paths = workspace_manager.get_paths(workspace_id)
    workspace_root = Path(paths['vector_store']).parent
    doc_folder = workspace_root / "processed_docs" / doc_folder_name
    
    if not doc_folder.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    summary_file = doc_folder / "summary.json"
    if not summary_file.exists():
        raise HTTPException(status_code=404, detail="Document summary not found")
    
    with open(summary_file, "r", encoding="utf-8") as f:
        summary = json.load(f)
    
    # Also load markdown content
    md_file = doc_folder / f"{doc_folder_name}.md"
    markdown_content = ""
    if md_file.exists():
        with open(md_file, "r", encoding="utf-8") as f:
            markdown_content = f.read()
    
    return {
        "summary": summary,
        "markdown": markdown_content
    }


@app.delete("/documents/processed/{doc_folder_name}")
def delete_processed_document(workspace_id: str, doc_folder_name: str):
    """Delete a processed document and all its files"""
    paths = workspace_manager.get_paths(workspace_id)
    workspace_root = Path(paths['vector_store']).parent
    doc_folder = workspace_root / "processed_docs" / doc_folder_name
    
    if not doc_folder.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        shutil.rmtree(doc_folder)
        return {"status": "success", "message": f"Document {doc_folder_name} deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")

@app.post("/academic/revise")
async def revise_chapter(draft: str, critique: str):
    """Auto-revises a draft based on critique"""
    from research.academic.editor import AcademicEditor
    editor = AcademicEditor()
    revised = editor.revise_chapter(draft, critique)
    return {"revised_draft": revised}

@app.get("/academic/experiments/{exp_id}/chart")
async def get_experiment_chart(exp_id: str, metric: str):
    """Generates and serves a chart for an experiment"""
    tracker = ExperimentTracker()
    chart_path = tracker.generate_chart(exp_id, metric)
    
    if chart_path and os.path.exists(chart_path):
        return FileResponse(chart_path)
    raise HTTPException(status_code=404, detail="Chart not found or metric missing")

@app.get("/academic/experiments")
def list_experiments():
    """List recent experiments"""
    tracker = ExperimentTracker()
    # Simple directory listing for MVP
    exps = []
    if os.path.exists(tracker.base_dir):
        for f in os.listdir(tracker.base_dir):
            if f.endswith(".json"):
                 exps.append(f.replace(".json", ""))
    return {"experiments": exps}

@app.post("/evolution/mode")
async def set_evolution_mode(mode: str):
    """
    Switches Twin mode: 'thesis' or 'exploration'
    """
    if digital_twin is None:
        return {"status": "error", "message": "DigitalTwin not available"}

    success = digital_twin.set_mode(mode)
    if not success:
        return {"status": "error", "message": "Invalid mode"}
    return {"status": "success", "mode": digital_twin.mode.value}

def get_workspace_files_dir(workspace_id: str) -> Path:
    ws_dir = Path(config.WORKSPACES_DIR) / workspace_id / "files"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return ws_dir

@app.post("/chat")
async def chat_with_knowledge(request: ChatRequest):
    """Chat coupled with RAG + Graph"""
    workspace_id = request.workspace_id
    rag_client, graph_engine = get_engines(workspace_id)

    # 1. Search Vector RAG
    results_vector = rag_client.search(request.message, top_k=3)
    vector_context = "\n".join([r['snippet'] for r in results_vector])
    
    # 2. Search Graph RAG
    graph_context = graph_engine.get_context(request.message)
    
    # 3. Combine Context
    full_context = f"""
    [Vector Knowledge]:
    {vector_context}
    
    [Graph Relationships]:
    {graph_context}
    """

    # --- JOURNAL SEARCH INTEGRATION ---
    # Heuristic: If user asks for "jurnal", "paper", "arxiv", "makalah"
    triggers = ["jurnal", "journal", "paper", "arxiv", "makalah", "research about"]
    msg_lower = request.message.lower()
    
    if any(t in msg_lower for t in triggers):
        try:
            print(f"[API] Journal Intent Detected: {request.message}")
            processor = JournalProcessor()
            # Extract topic roughly (User: "Cari jurnal tentang X" -> "X")
            # For MVP, just pass the whole message, the searcher handles it well enough
            journal_result = processor.process_query(request.message, max_papers=1)
            
            if journal_result["status"] == "success":
                papers_context = ""
                for p in journal_result["papers"]:
                    papers_context += f"\n[PAPER] {p['metadata']['title']}\nSummary: {p['metadata']['summary'][:500]}...\nInsight: {p['insight']}\n"
                
                full_context += f"\n\n[LIVE ACADEMIC PAPERS]:\n{papers_context}"
                print(f"[API] Injected {len(journal_result['papers'])} papers into context.")
            else:
                full_context += f"\n\n[LIVE ACADEMIC PAPERS]: No papers found for this topic."
        except Exception as e:
            print(f"[API] Journal Processing Error: {e}")
            full_context += f"\n\n[LIVE ACADEMIC PAPERS]: Error during search ({str(e)})."
    # ----------------------------------
    
    # 4. Synthesize with Teacher
    from teacher import Teacher
    # Use 'reasoning' for deep synthesis, or 'chat' for faster response?
    # Let's use 'reasoning' for high quality RAG synthesis
    teacher = Teacher(model_type="reasoning")
    
    prompt = f"""
    Context: 
    {full_context}
    
    User Question: {request.message}
    
    Answer based on the combined context (Vector + Graph + Papers). 
    If the context is insufficient, rely on your internal knowledge but mention that it's general knowledge.
    Format your answer nicely with Markdown.
    """
    
    system_instruction = (
        "You are JAYA, an advanced AI Research Assistant. You help users understand complex topics by synthesizing information "
        "from their knowledge base (Vector Store & Knowledge Graph) and academic papers. Be helpful, precise, and scientific. "
        "\n\n"
        "CORE TOOL CAPABILITY: You have a tool to write/create files in the user's workspace directory. "
        "Whenever the user asks you to write, save, or create a file (such as a markdown document, outline, script, report, notes, etc.), "
        "you MUST write the content of the file and wrap it EXACTLY inside a `<create_file name=\"filename.ext\">...</create_file>` block. "
        "For example:\n"
        "<create_file name=\"outline.md\">\n"
        "# Outline Tugas Akhir\n"
        "1. Pendahuluan\n"
        "</create_file>\n"
        "You can write multiple files in a single response if requested. The file names must be simple and clean (e.g., report.md, script.py)."
    )
    
    answer = teacher.ask(prompt, system_instruction=system_instruction)
    
    # 5. Extract and save generated files
    import re
    files_dir = get_workspace_files_dir(workspace_id)
    
    # We match: <create_file name="filename.ext">content</create_file>
    # or <write_file name="filename.ext">content</write_file>
    pattern = re.compile(r'<(create_file|write_file)\s+name="([^"]+)"\s*>(.*?)</\1>', re.DOTALL)
    matches = pattern.findall(answer)
    
    for tag_type, filename, content in matches:
        # Sanitize to prevent path traversal
        safe_filename = Path(filename).name
        filepath = files_dir / safe_filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content.strip())
        print(f"[API] File generated via chat tool: {safe_filename} in workspace {workspace_id}")
        
    # Clean up the XML tags from the visible answer so it looks nice
    clean_answer = answer
    for tag_type, filename, content in matches:
        notice = f"\n\n> 📁 **File Generated successfully:** `{filename}` (Tersedia di panel kanan untuk Preview & Download)\n\n"
        escaped_filename = re.escape(filename)
        clean_answer = re.sub(
            rf'<{tag_type}\s+name="{escaped_filename}"\s*>.*?</{tag_type}>',
            notice,
            clean_answer,
            flags=re.DOTALL
        )
    
    return {
        "answer": clean_answer,
        "sources": [r['document'].get('file_name', 'Unknown') for r in results_vector] + ["Knowledge Graph"]
    }

@app.get("/documents")
def list_documents(workspace_id: str = "default"):
    """
    List all documents in the workspace files directory.
    This implements the files panel listing on the right of the ChatPage.
    """
    files_dir = get_workspace_files_dir(workspace_id)
    files = []
    
    if files_dir.exists():
        for item in files_dir.iterdir():
            if item.is_file():
                stat = item.stat()
                files.append({
                    "name": item.name,
                    "size": stat.st_size,
                    "updated_at": stat.st_mtime,
                    "type": item.suffix.lstrip('.').lower() or "txt",
                    "source": "generated"
                })
                
    # Sort files by update time (newest first)
    files.sort(key=lambda x: x["updated_at"], reverse=True)
    return files

@app.get("/documents/view/{workspace_id}/{filename}")
def view_document(workspace_id: str, filename: str):
    """
    Serve a file's raw content.
    Used for downloading or previewing generated files in the UI.
    """
    files_dir = get_workspace_files_dir(workspace_id)
    safe_filename = Path(filename).name
    filepath = files_dir / safe_filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(filepath, filename=safe_filename)

@app.delete("/documents/delete/{workspace_id}/{filename}")
def delete_document(workspace_id: str, filename: str):
    """
    Delete a document/file from the workspace files directory.
    """
    files_dir = get_workspace_files_dir(workspace_id)
    safe_filename = Path(filename).name
    filepath = files_dir / safe_filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        filepath.unlink()
        return {"status": "success", "message": f"File '{safe_filename}' deleted."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/upload/{workspace_id}")
async def upload_document_to_workspace(workspace_id: str, file: UploadFile = File(...)):
    """
    Upload a file directly to the workspace files directory.
    """
    files_dir = get_workspace_files_dir(workspace_id)
    safe_filename = Path(file.filename).name
    filepath = files_dir / safe_filename
    
    try:
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {
            "status": "success",
            "filename": safe_filename,
            "message": f"File '{safe_filename}' uploaded successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ingest/video")
async def ingest_video(request: VideoIngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest Youtube video using AI-Q Video Analysis Logic
    """
    try:
        from research.video_processor import VideoProcessor as _VP
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Fitur video tidak aktif (dependency opsional tidak terpasang: {e}). "
                   "Install dengan: pip install opencv-python yt-dlp static-ffmpeg"
        )

    def process(url):
        processor = _VP()
        result = processor.process_video(url)

        # Store in Memory
        from memory import DiscoveryMemory
        memory = DiscoveryMemory(config.DISCOVERY_MEMORY_PATH)
        memory.add_experience(
            code=result['report'],
            result="VIDEO_ANALYSIS",
            metadata={
                "type": "video",
                "title": result['title'],
                "url": url,
                "video_path": result['video_path']
            }
        )
        print(f"[API] Video ingestion complete: {result['title']}")

    background_tasks.add_task(process, request.url)
    return {"status": "processing", "message": "Video analysis started in background"}

@app.post("/debate")
async def start_debate(request: DebateRequest):
    """
    Simulate a debate on a topic.
    """
    # Simple Mock/Heuristic Debate for MVP
    # In production, this would call LLM twice with different system prompts
    
    topic = request.topic
    
    # We can use the Teacher/Research Agent to generate this content
    # For speed, let's use a simple template structure populated by one LLM call
    
    from teacher import Teacher
    teacher = Teacher()
    
    prompt = f"""
    Simulate a debate between two AI personas about: "{topic}"
    
    Persona 1 ({request.persona_1}): Needs to argue FOR the topic or be optimistic.
    Persona 2 ({request.persona_2}): Needs to argue AGAINST the topic or be skeptical.
    
    Generate {request.rounds} rounds of dialogue.
    Format as JSON list: [{{ "speaker": "Persona 1", "text": "..." }}, {{ "speaker": "Persona 2", "text": "..." }}]
    """
    
    # Using ask for generic generation
    # Ideally, Teacher should have a proper 'generate' method
    result_text = teacher.ask(prompt, system_instruction=f"You are a Moderator simulating a debate between {request.persona_1} and {request.persona_2}.")
    
    # Try to parse or just return text
    # Since teacher returns string, we might need to parse it if we want structured data
    # For now, let's return the raw text or try to make it structured on frontend
    
    return {
        "topic": topic,
        "debate_transcript": result_text
    }

@app.get("/graph")
def get_knowledge_graph(workspace_id: str = "default"):
    """Get knowledge graph for visualization"""
    try:
        _, graph_engine = get_engines(workspace_id)
        return graph_engine.get_viz_data()
    except Exception as e:
        print(f"Graph Error: {e}")
        return {"nodes": [], "edges": []}

@app.get("/research/journals/citation-graph")
def get_citation_graph_data():
    """
    Get the full citation graph (paper → references) for React Flow visualisation.
    Different from /graph which shows knowledge triples.
    """
    try:
        from research.academic.citation_graph import get_citation_graph
        cg = get_citation_graph()
        return cg.get_viz_data()
    except Exception as e:
        print(f"[API] Citation graph error: {e}")
        return {"nodes": [], "edges": []}

@app.get("/research/journals/cache")
def get_cached_journals():
    """
    List all journals that have been previously processed and cached.
    Returns paper metadata including local paths and insight excerpts.
    """
    try:
        from research.academic.journal_processor import PaperCache
        cache = PaperCache()
        papers = cache.list_all()
        from research.academic.citation_graph import get_citation_graph
        cg = get_citation_graph()
        stats = cg.get_stats()
        return {
            "status": "success",
            "count": len(papers),
            "papers": papers,
            "graph_stats": stats,
        }
    except Exception as e:
        print(f"[API] Cache list error: {e}")
        return {"status": "error", "message": str(e), "papers": []}

class FindCachedRequest(BaseModel):
    query: str
    top_k: int = 5

@app.post("/research/journals/find-cached")
def find_cached_journals(request: FindCachedRequest):
    """
    Search cached journals by keyword before triggering a new download.
    UI can call this to check if relevant papers are already available locally.
    """
    try:
        from research.academic.journal_processor import PaperCache
        from research.academic.citation_graph import get_citation_graph
        cache = PaperCache()
        results = cache.search(request.query, top_k=request.top_k)
        # Also search citation graph for broader matches
        cg = get_citation_graph()
        graph_results = cg.search_by_query(request.query, top_k=request.top_k)
        return {
            "status": "success",
            "query": request.query,
            "cache_hits": results,
            "graph_hits": graph_results,
            "total_hits": len(results),
        }
    except Exception as e:
        print(f"[API] Find cached error: {e}")
        return {"status": "error", "message": str(e), "cache_hits": []}

@app.get("/evolution/status")
async def get_evolution_status():
    """Get the current state of the Digital Twin"""
    if digital_twin is None:
        return {"status": "unavailable", "message": "DigitalTwin not initialized"}

    recent_thoughts = digital_twin.memory.get_recent_thoughts(limit=5)
    return {
        "state": digital_twin.state.value,
        "is_awake": getattr(digital_twin, 'running', False),
        "latest_thought": recent_thoughts[-1] if recent_thoughts else None,
        "recent_history": recent_thoughts
    }

@app.get("/evolution/logs")
async def get_evolution_logs(limit: int = 50):
    """Get full history of Twin's thoughts"""
    if digital_twin is None:
        return {"status": "unavailable", "message": "DigitalTwin not initialized"}
    return digital_twin.memory.get_recent_thoughts(limit=limit)

@app.post("/evolution/night_mode")
def set_night_mode(enabled: bool):
    if digital_twin is None:
        return {"status": "unavailable", "message": "DigitalTwin not initialized"}
    digital_twin.toggle_night_mode(enabled)
    return {"status": "success", "night_mode": enabled}

@app.get("/history")
def get_history():
    """Get past research reports"""
    global meta_analyst
    if meta_analyst is None:
        meta_analyst = MetaAnalyst()
    return meta_analyst.get_research_history()


# ─── DYNAMIC MODEL CONFIGURATION ──────────────────────────────────────────────

class ModelConfigRequest(BaseModel):
    model_name: str

@app.get("/config/models")
def get_config_models():
    """
    Fetch list of available models from integrate.api.nvidia.com 
    and get the currently active model.
    """
    from teacher import get_override_model
    import os
    
    # Get active model
    active_model = get_override_model() or os.getenv("NVIDIA_LLAMA31_MODEL") or config.NVIDIA_REASONING_MODEL
    
    # Get list of models from NVIDIA API
    available_models = []
    try:
        api_key = os.getenv("NVIDIA_API_KEY")
        base_url = os.getenv("NVIDIA_LLAMA31_BASE_URL", config.NVIDIA_BASE_URL)
        if api_key:
            from openai import OpenAI
            client = OpenAI(base_url=base_url, api_key=api_key)
            models = client.models.list()
            # Ambil semua model yang tersedia
            available_models = [m.id for m in models]
            available_models.sort()
    except Exception as e:
        print(f"[API] Error listing NVIDIA models: {e}")
        # Fallback list jika API list gagal
        available_models = [
            config.NVIDIA_REASONING_MODEL,
            config.NVIDIA_CHAT_MODEL,
            config.NVIDIA_CODING_MODEL,
            config.NVIDIA_VISION_MODEL,
        ]
        
    return {
        "active_model": active_model,
        "available_models": available_models
    }

@app.post("/config/models")
def update_config_model(request: ModelConfigRequest):
    """
    Update the active reasoning model.
    """
    from teacher import set_override_model
    set_override_model(request.model_name)
    return {
        "status": "success",
        "active_model": request.model_name
    }


# ============================================================
# THESIS UPLOAD & ANALYSIS ENDPOINTS
# ============================================================

# In-memory store untuk progress analisis: session_id -> status dict
_thesis_sessions: dict = {}

THESIS_UPLOADS_DIR = ROOT_DIR / "data" / "thesis_uploads"
THESIS_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _extract_pdf_text(file_path: str) -> str:
    """
    Extract text dari PDF. Mencoba PyMuPDF dulu, lalu pdfplumber, lalu raw bytes.
    """
    text = ""

    # Coba PyMuPDF (fitz) - tercepat
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text())
        text = "\n\n".join(pages)
        doc.close()
        print(f"[ThesisAPI] Extracted {len(text)} chars via PyMuPDF")
        return text
    except ImportError:
        print("[ThesisAPI] PyMuPDF not available, trying pdfplumber...")
    except Exception as e:
        print(f"[ThesisAPI] PyMuPDF error: {e}, trying pdfplumber...")

    # Fallback ke pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        text = "\n\n".join(pages)
        print(f"[ThesisAPI] Extracted {len(text)} chars via pdfplumber")
        return text
    except ImportError:
        print("[ThesisAPI] pdfplumber not available, trying pypdf2...")
    except Exception as e:
        print(f"[ThesisAPI] pdfplumber error: {e}")

    # Fallback ke PyPDF2
    try:
        import PyPDF2
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)
        print(f"[ThesisAPI] Extracted {len(text)} chars via PyPDF2")
        return text
    except ImportError:
        print("[ThesisAPI] PyPDF2 not available either.")
    except Exception as e:
        print(f"[ThesisAPI] PyPDF2 error: {e}")

    raise HTTPException(
        status_code=422,
        detail="Tidak bisa mengekstrak teks dari PDF. Install: pip install pymupdf pdfplumber"
    )


@app.post("/thesis/upload")
async def upload_thesis(
    file: UploadFile = File(...),
    workspace_id: str = "default"
):
    """
    Upload PDF Tugas Akhir. Simpan ke disk, ekstrak teks, dan kembalikan session_id
    yang bisa digunakan untuk memanggil /thesis/analyze.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima.")

    # Simpan file
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in file.filename)
    dest_path = THESIS_UPLOADS_DIR / safe_name
    with open(dest_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    print(f"[ThesisAPI] File saved: {dest_path} ({dest_path.stat().st_size} bytes)")

    # Ekstrak teks
    raw_text = _extract_pdf_text(str(dest_path))
    page_count = raw_text.count("\n\n") + 1  # rough estimate

    # Simpan teks ke sesi
    import uuid
    session_id = str(uuid.uuid4())
    _thesis_sessions[session_id] = {
        "status": "uploaded",
        "file_name": safe_name,
        "file_path": str(dest_path),
        "workspace_id": workspace_id,
        "raw_text": raw_text,
        "char_count": len(raw_text),
        "analysis": None,
        "error": None,
    }

    # Ingest ke vector store workspace agar bisa di-chat
    try:
        rag_client, graph_engine = get_engines(workspace_id)
        rag_client.ingest_text(raw_text, metadata={"source": "thesis", "file_name": safe_name})
        graph_engine.ingest_document(raw_text[:4000], f"Thesis: {safe_name}")
        print(f"[ThesisAPI] Ingested to RAG workspace={workspace_id}")
    except Exception as e:
        print(f"[ThesisAPI] RAG ingest warning (non-fatal): {e}")

    return {
        "session_id": session_id,
        "file_name": safe_name,
        "char_count": len(raw_text),
        "status": "uploaded",
        "message": "File berhasil diupload dan teks berhasil diekstrak. Siap untuk dianalisis.",
    }


@app.post("/thesis/analyze/{session_id}")
async def analyze_thesis(session_id: str, background_tasks: BackgroundTasks):
    """
    Jalankan analisis komprehensif Tugas Akhir:
    1. Ekstrak judul, abstrak, topik (LLM)
    2. Cek novelty vs literatur (NoveltyChecker)
    3. Cari research gap (GapFinder)
    4. Critique chapter (ReviewerAgent)
    5. Generate defense questions
    """
    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan. Upload file terlebih dahulu.")

    sess = _thesis_sessions[session_id]
    if sess["status"] == "analyzing":
        return {"status": "analyzing", "message": "Analisis sedang berjalan..."}

    sess["status"] = "analyzing"
    sess["progress"] = 0
    sess["steps"] = []

    def run_analysis(sid: str):
        s = _thesis_sessions[sid]
        text = s["raw_text"]
        # Ambil 8000 karakter pertama untuk LLM (token budget)
        excerpt = text[:8000]

        try:
            from teacher import Teacher
            brain = Teacher(model_type="reasoning")

            # Step 1: Meta extraction
            s["progress"] = 10
            s["steps"].append({"step": "meta", "status": "running", "label": "Mengekstrak metadata..."})
            meta_prompt = f"""
Ekstrak informasi berikut dari dokumen Tugas Akhir di bawah ini dalam format JSON:
{{
  "judul": "...",
  "penulis": "...",
  "abstrak": "...",
  "topik_utama": "...",
  "metode": "...",
  "keywords": ["...", "..."]
}}

DOKUMEN (potongan awal):
{excerpt[:3000]}
"""
            meta_raw = brain.ask(meta_prompt)
            # Parse JSON dari respons LLM
            meta = {}
            try:
                # Cari blok JSON di respons
                import re
                json_match = re.search(r'\{.*\}', meta_raw, re.DOTALL)
                if json_match:
                    meta = json.loads(json_match.group())
            except Exception:
                meta = {"judul": s["file_name"], "topik_utama": "Tidak terdeteksi", "abstrak": excerpt[:500]}

            s["meta"] = meta
            s["steps"][-1]["status"] = "done"
            print(f"[ThesisAPI] Meta: {meta.get('judul', 'N/A')}")

            topic = meta.get("topik_utama", "AI Research")
            abstract = meta.get("abstrak", excerpt[:1000])

            # Step 2: Novelty check
            s["progress"] = 25
            s["steps"].append({"step": "novelty", "status": "running", "label": "Memeriksa novelty..."})
            novelty_result = {}
            try:
                from research.academic.novelty_checker import NoveltyChecker
                checker = NoveltyChecker()
                # Run async in sync context
                loop = asyncio.new_event_loop()
                novelty_result = loop.run_until_complete(
                    checker.verify_novelty(abstract, keywords=meta.get("keywords", []))
                )
                loop.close()
            except Exception as e:
                print(f"[ThesisAPI] Novelty check error: {e}")
                novelty_result = {"is_novel": None, "confidence": 0, "reasoning": f"Error: {e}"}
            s["novelty"] = novelty_result
            s["steps"][-1]["status"] = "done"

            # Step 3: Gap analysis
            s["progress"] = 45
            s["steps"].append({"step": "gap", "status": "running", "label": "Mengidentifikasi research gap..."})
            gap_report = ""
            try:
                from research.academic.gap_finder import GapFinder
                finder = GapFinder()
                finder.build_network(topic, depth=1)
                gap_report = finder.analyze_gaps()
            except Exception as e:
                print(f"[ThesisAPI] Gap finder error: {e}")
                gap_report = f"Tidak bisa menjalankan analisis gap: {e}"
            s["gap_report"] = gap_report
            s["steps"][-1]["status"] = "done"

            # Step 4: Critique
            s["progress"] = 65
            s["steps"].append({"step": "critique", "status": "running", "label": "Mengkritisi draft..."})
            critique = ""
            try:
                from research.academic.reviewer import ReviewerAgent
                reviewer = ReviewerAgent()
                critique = reviewer.critique_chapter(excerpt, topic)
            except Exception as e:
                print(f"[ThesisAPI] Critique error: {e}")
                critique = f"Tidak bisa menjalankan kritik: {e}"
            s["critique"] = critique
            s["steps"][-1]["status"] = "done"

            # Step 5: Defense questions
            s["progress"] = 85
            s["steps"].append({"step": "defense", "status": "running", "label": "Membuat pertanyaan sidang..."})
            defense_questions = ""
            try:
                from research.academic.reviewer import ReviewerAgent
                reviewer2 = ReviewerAgent()
                defense_questions = reviewer2.generate_defense_questions(topic, abstract)
            except Exception as e:
                print(f"[ThesisAPI] Defense questions error: {e}")
                defense_questions = f"Tidak bisa membuat pertanyaan: {e}"
            s["defense_questions"] = defense_questions
            s["steps"][-1]["status"] = "done"

            # Done
            s["progress"] = 100
            s["status"] = "done"
            s["analysis"] = {
                "meta": s.get("meta", {}),
                "novelty": s.get("novelty", {}),
                "gap_report": s.get("gap_report", ""),
                "critique": s.get("critique", ""),
                "defense_questions": s.get("defense_questions", ""),
            }
            # Jangan simpan raw_text di hasil (hemat memori response)
            print(f"[ThesisAPI] Analysis complete for session {sid}")

        except Exception as e:
            import traceback
            s["status"] = "error"
            s["error"] = str(e)
            print(f"[ThesisAPI] Analysis FAILED: {e}\n{traceback.format_exc()}")

    background_tasks.add_task(run_analysis, session_id)
    return {"status": "analyzing", "session_id": session_id, "message": "Analisis dimulai di background."}


@app.get("/thesis/status/{session_id}")
def get_thesis_status(session_id: str):
    """Polling endpoint untuk progress analisis."""
    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")
    s = _thesis_sessions[session_id]
    return {
        "session_id": session_id,
        "status": s.get("status"),
        "progress": s.get("progress", 0),
        "steps": s.get("steps", []),
        "file_name": s.get("file_name"),
        "char_count": s.get("char_count", 0),
        "analysis": s.get("analysis"),
        "error": s.get("error"),
    }


@app.post("/thesis/chat/{session_id}")
async def chat_with_thesis(session_id: str, request: ChatRequest):
    """Tanya-jawab langsung dengan isi dokumen Tugas Akhir via RAG."""
    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    sess = _thesis_sessions[session_id]
    workspace_id = sess.get("workspace_id", "default")
    raw_text = sess.get("raw_text", "")

    # Ambil konteks relevan dari RAG jika tersedia
    rag_context = ""
    try:
        rag_client, _ = get_engines(workspace_id)
        results = rag_client.search(request.message, top_k=5)
        rag_context = "\n".join([r['snippet'] for r in results])
    except Exception:
        pass

    # Fallback: ambil langsung dari teks
    if not rag_context:
        rag_context = raw_text[:5000]

    from teacher import Teacher
    brain = Teacher(model_type="reasoning")
    prompt = f"""
Kamu adalah asisten analisis Tugas Akhir. Bantu menjawab pertanyaan berikut berdasarkan dokumen TA yang sudah diupload.

KONTEKS DARI DOKUMEN TA:
{rag_context}

PERTANYAAN: {request.message}

Jawab dengan detail, referensikan bagian dokumen yang relevan jika bisa.
"""
    answer = brain.ask(prompt)
    return {"answer": answer, "sources": [sess.get("file_name", "thesis.pdf")]}


# ─── REVISI BAGIAN TA ────────────────────────────────────────────────────────

class ThesisReviseRequest(BaseModel):
    section_text: str          # Teks bagian TA yang mau direvisi
    instruction: str           # Instruksi: "perbaiki flow", "tambah referensi", dll.
    revision_type: str = "general"  # general | formal | citation | methodology


@app.post("/thesis/revise/{session_id}")
async def revise_thesis_section(session_id: str, request: ThesisReviseRequest):
    """
    Revisi bagian tertentu dari Tugas Akhir berdasarkan instruksi pengguna.
    Menggunakan AcademicEditor yang sudah ada + konteks dari analisis sebelumnya.
    """
    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan. Upload file terlebih dahulu.")

    sess = _thesis_sessions[session_id]
    meta = sess.get("meta", {})
    topic = meta.get("topik_utama", "")
    critique = sess.get("critique", "")

    # Buat prompt revisi yang kontekstual berdasarkan tipe
    type_instructions = {
        "general":     "Perbaiki kejelasan, alur, dan kualitas akademis secara umum.",
        "formal":      "Ubah bahasa menjadi lebih formal dan akademis. Hilangkan bahasa kasual.",
        "citation":    "Identifikasi klaim yang perlu sitasi dan tambahkan placeholder [Citation Needed] dengan saran sumber.",
        "methodology": "Perkuat bagian metodologi — pastikan langkah-langkah penelitian logis dan reproducible.",
    }
    type_hint = type_instructions.get(request.revision_type, type_instructions["general"])

    # Gunakan critique dari analisis sebelumnya sebagai context tambahan
    critique_context = f"\n\nCATATAN DARI REVIEWER SEBELUMNYA:\n{critique[:2000]}" if critique else ""

    try:
        from research.academic.editor import AcademicEditor
        editor = AcademicEditor()

        combined_instruction = f"{request.instruction}\n\nTipe revisi: {type_hint}{critique_context}"
        revised = editor.revise_chapter(request.section_text, combined_instruction, context=topic)

        # Simpan riwayat revisi ke sesi
        if "revisions" not in sess:
            sess["revisions"] = []
        sess["revisions"].append({
            "original": request.section_text[:500],  # simpan preview saja
            "instruction": request.instruction,
            "type": request.revision_type,
            "revised_preview": revised[:500],
        })

        return {
            "revised_text": revised,
            "revision_type": request.revision_type,
            "session_id": session_id,
        }
    except Exception as e:
        import traceback
        print(f"[ThesisAPI] Revise error: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Revisi gagal: {e}")


# ─── PENCARIAN JURNAL RELEVAN ─────────────────────────────────────────────────

@app.post("/thesis/journals/{session_id}")
async def find_relevant_journals(session_id: str, max_papers: int = 10):
    """
    Cari jurnal dan paper akademis yang relevan dengan topik Tugas Akhir.
    Menggunakan ArXiv + Semantic Scholar berdasarkan metadata yang sudah dianalisis.
    """
    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    sess = _thesis_sessions[session_id]
    meta = sess.get("meta", {})
    topic = meta.get("topik_utama", "")
    keywords = meta.get("keywords", [])

    if not topic and not keywords:
        raise HTTPException(status_code=400, detail="Analisis belum selesai. Jalankan /thesis/analyze terlebih dahulu.")

    # Buat query dari topik + keywords
    search_queries = [topic] + keywords[:3]

    results = []

    try:
        from research.academic.literature import ArxivClient, SemanticScholarClient
        arxiv = ArxivClient()
        scholar = SemanticScholarClient()

        for query in search_queries[:2]:  # max 2 query untuk efisiensi
            if not query:
                continue

            # ArXiv search
            try:
                arxiv_papers = arxiv.search_papers(query, max_results=max_papers // 2)
                for p in arxiv_papers:
                    results.append({
                        "source": "ArXiv",
                        "title": p.get("title", ""),
                        "authors": p.get("authors", []),
                        "year": p.get("published", "")[:4] if p.get("published") else "",
                        "abstract": p.get("summary", "")[:300],
                        "url": p.get("url", ""),
                        "id": p.get("id", ""),
                        "relevance_query": query,
                    })
            except Exception as e:
                print(f"[ThesisAPI] ArXiv search error: {e}")

            # Semantic Scholar search
            try:
                ss_papers = scholar.search_papers(query, max_results=max_papers // 2)
                for p in ss_papers:
                    results.append({
                        "source": "Semantic Scholar",
                        "title": p.get("title", ""),
                        "authors": p.get("authors", []),
                        "year": p.get("year", ""),
                        "abstract": p.get("summary", p.get("abstract", ""))[:300],
                        "url": p.get("url", f"https://www.semanticscholar.org/paper/{p.get('id', '')}"),
                        "id": p.get("id", ""),
                        "relevance_query": query,
                    })
            except Exception as e:
                print(f"[ThesisAPI] Semantic Scholar search error: {e}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pencarian jurnal gagal: {e}")

    # Deduplicate berdasarkan title
    seen_titles = set()
    unique_results = []
    for r in results:
        title_key = r["title"].lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_results.append(r)

    # Simpan ke sesi
    sess["journals"] = unique_results

    return {
        "session_id": session_id,
        "topic": topic,
        "queries_used": [q for q in search_queries[:2] if q],
        "total": len(unique_results),
        "papers": unique_results[:max_papers],
    }


# ─── EKSPOR LAPORAN ──────────────────────────────────────────────────────────

@app.get("/thesis/export/{session_id}")
async def export_thesis_report(session_id: str):
    """
    Compile semua hasil analisis menjadi laporan Markdown lengkap yang bisa didownload.
    """
    from fastapi.responses import Response

    if session_id not in _thesis_sessions:
        raise HTTPException(status_code=404, detail="Session tidak ditemukan.")

    sess = _thesis_sessions[session_id]
    analysis = sess.get("analysis")

    if not analysis:
        raise HTTPException(status_code=400, detail="Analisis belum selesai. Jalankan /thesis/analyze terlebih dahulu.")

    meta = analysis.get("meta", {})
    novelty = analysis.get("novelty", {})
    gap = analysis.get("gap_report", "")
    critique = analysis.get("critique", "")
    defense = analysis.get("defense_questions", "")
    journals = sess.get("journals", [])

    # Buat tanggal
    from datetime import datetime
    now = datetime.now().strftime("%d %B %Y, %H:%M")

    # Susun laporan Markdown
    report_lines = [
        f"# Laporan Analisis Tugas Akhir",
        f"",
        f"> Dihasilkan oleh **JAYA Research** pada {now}",
        f"> File: `{sess.get('file_name', 'thesis.pdf')}`",
        f"",
        f"---",
        f"",
    ]

    # Metadata
    if meta:
        report_lines += [
            f"## 📋 Informasi Dokumen",
            f"",
            f"| Field | Value |",
            f"|---|---|",
            f"| **Judul** | {meta.get('judul', '-')} |",
            f"| **Penulis** | {meta.get('penulis', '-')} |",
            f"| **Topik Utama** | {meta.get('topik_utama', '-')} |",
            f"| **Metode** | {meta.get('metode', '-')} |",
        ]
        if meta.get("keywords"):
            kws = ", ".join(f"`{k}`" for k in meta["keywords"])
            report_lines += [f"| **Keywords** | {kws} |"]
        report_lines += [f"", f"### Abstrak", f"", meta.get("abstrak", "-"), f""]

    # Novelty
    if novelty:
        is_novel = novelty.get("is_novel")
        pct = int((novelty.get("confidence", 0)) * 100)
        badge = "✅ NOVEL" if is_novel else ("❌ KURANG NOVEL" if is_novel is False else "⚠️ TIDAK TERDETEKSI")
        report_lines += [
            f"## 🔬 Analisis Novelty",
            f"",
            f"**Status**: {badge} (Confidence: {pct}%)",
            f"",
            f"**Reasoning**:",
            f"",
            novelty.get("reasoning", "-"),
            f"",
        ]

    # Research Gap
    if gap:
        report_lines += [
            f"## 📈 Research Gap & Peluang",
            f"",
            gap,
            f"",
        ]

    # Critique
    if critique:
        report_lines += [
            f"## ⚔️ Kritik Akademis (Peer Review)",
            f"",
            critique,
            f"",
        ]

    # Defense Questions
    if defense:
        report_lines += [
            f"## 🛡️ Pertanyaan Sidang yang Mungkin Muncul",
            f"",
            defense,
            f"",
        ]

    # Jurnal Relevan
    if journals:
        report_lines += [
            f"## 📚 Jurnal Relevan",
            f"",
        ]
        for i, paper in enumerate(journals[:15], 1):
            year = f" ({paper['year']})" if paper.get("year") else ""
            url = f" — [Link]({paper['url']})" if paper.get("url") else ""
            report_lines += [
                f"### {i}. {paper.get('title', 'Untitled')}{year}",
                f"",
                f"**Sumber**: {paper.get('source', '-')}{url}",
                f"",
                paper.get("abstract", "") or "_Abstrak tidak tersedia._",
                f"",
            ]

    # Riwayat Revisi
    revisions = sess.get("revisions", [])
    if revisions:
        report_lines += [
            f"## 📝 Riwayat Revisi",
            f"",
        ]
        for i, rev in enumerate(revisions, 1):
            report_lines += [
                f"### Revisi {i} — `{rev.get('type', 'general')}`",
                f"",
                f"**Instruksi**: {rev.get('instruction', '-')}",
                f"",
                f"**Preview teks asli**: _{rev.get('original', '')[:200]}..._",
                f"",
            ]

    report_lines += [
        f"---",
        f"",
        f"*Laporan ini dihasilkan secara otomatis oleh JAYA Research. Selalu verifikasi hasil dengan pembimbing.*",
    ]

    report_md = "\n".join(report_lines)

    # Kembalikan sebagai file download
    file_name = f"jaya_analysis_{sess.get('file_name', 'thesis').replace('.pdf', '')}.md"
    return Response(
        content=report_md.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=\"{file_name}\""},
    )


# ─── EVOLUTION & AUTO-UPGRADE ENDPOINTS ─────────────────────────

_latest_upgrade_result = None
_is_autonomous_loop_running = False
_auto_loop_task = None
_loop_iteration_count = 0
_loop_is_busy = False  # prevent concurrent executions

def _do_auto_upgrade_sync(custom_topic: Optional[str] = None):
    """Synchronous core auto-upgrade logic to be executed in thread pool."""
    global _latest_upgrade_result
    import sys
    import random
    from pathlib import Path
    src_dir = Path(__file__).resolve().parent.parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(src_dir / "research") not in sys.path:
        sys.path.insert(0, str(src_dir / "research"))

    from research.hypothesis_generator import HypothesisGenerator, TOPIC_POOL
    from research.experiment_designer import ExperimentDesigner
    from research.experiment_runner import ExperimentRunner
    from research.learning_from_results import LearningFromResults
    from research.jarvis_discovery_bridge import JarvisDiscoveryBridge

    # 1. Dynamic Topic Selection with unique seed per call
    seed = int(time.time() * 1000) % (2**32)
    rng = random.Random(seed)
    selected_topic = custom_topic or rng.choice(TOPIC_POOL)

    # 2. Dynamic Hypothesis Generation
    hyp_gen = HypothesisGenerator()
    hypothesis = hyp_gen.generate_hypothesis(
        topic=selected_topic,
        context=f"JAYA_CORE AGI optimization constraint < 200MB memory, latency < 100ms, seed: {seed}, ts: {time.time():.6f}"
    )

    # Ensure hypothesis_id is globally unique
    import uuid
    from datetime import datetime as _dt
    hyp_uid = uuid.uuid4().hex[:8].upper()
    hypothesis["hypothesis_id"] = f"HYP-{_dt.now().strftime('%Y%m%d-%H%M%S')}-{hyp_uid}"

    # 3. Experiment Design
    designer = ExperimentDesigner()
    exp_plan = designer.design_experiment(hypothesis)

    # 4. Trial Runner & Bayesian Update
    runner = ExperimentRunner()
    trial_res = runner.run_experiment(exp_plan)
    
    learner = LearningFromResults()
    prior = round(rng.uniform(0.42, 0.58), 2)
    post, delta, rec, summary = learner.update_hypothesis_confidence(hypothesis, trial_res, prior_confidence=prior)

    # 5. JARVIS Discovery Bridge — unique patch ID per call
    db_path = src_dir.parent / "data" / "agentic_jarvis.db"
    bridge = JarvisDiscoveryBridge(core_db_path=db_path)
    
    learning_analysis = {
        "posterior_confidence": post,
        "recommendation": rec,
        "summary": summary
    }
    patch = bridge.create_jarvis_patch(hypothesis, learning_analysis)

    # Override patch_id with guaranteed-unique value
    patch["patch_id"] = f"JAYPATCH-{_dt.now().strftime('%Y%m%d-%H%M%S')}-{hyp_uid}"
    patch["llm_generated"] = hypothesis.get("llm_generated", False)
    patch["novelty_score"] = hypothesis.get("novelty_score", 0.85)

    applied = bridge.apply_patch_to_core(patch)

    res = {
        "patch_id": patch["patch_id"],
        "topic": selected_topic,
        "target_system": patch.get("target_system", "JAYA_CORE_BRAIN"),
        "bayes_confidence": round(post, 4),
        "novelty_score": hypothesis.get("novelty_score", 0.85),
        "statement": hypothesis["statement"],
        "llm_generated": hypothesis.get("llm_generated", False),
        "recommendation": rec,
        "sqlite_injection_success": applied,
        "hypothesis_id": hypothesis["hypothesis_id"],
        "iteration": _loop_iteration_count,
        "timestamp": time.time()
    }
    
    _latest_upgrade_result = res
    print(f"[AUTO-UPGRADE] ✅ Patch {patch['patch_id']} applied to DB: {applied}")
    return res

async def _continuous_autonomous_research_worker():
    global _is_autonomous_loop_running, _loop_iteration_count, _loop_is_busy
    print("[AUTONOMOUS LOOP] 🚀 Continuous Research Loop Started!")
    while _is_autonomous_loop_running:
        if not _loop_is_busy:
            _loop_is_busy = True
            _loop_iteration_count += 1
            iteration = _loop_iteration_count
            try:
                print(f"[AUTONOMOUS LOOP] ▶ Iteration #{iteration}")
                # 1. Run Autonomous Discovery & SQLite Patch Injection in thread
                await asyncio.to_thread(_do_auto_upgrade_sync)

                # 2. Periodically trigger Autonomous LoRA Fine-Tuning & Memory Manager (every 5 iterations)
                if iteration % 5 == 0:
                    print(f"[AUTONOMOUS LOOP] 🧬 Triggering Auto LoRA Fine-Tuning & Memory Manager Sync (Iteration #{iteration})...")
                    from auto_finetune import run_auto_finetune_cycle
                    from memory_manager import MemoryManager

                    await asyncio.to_thread(run_auto_finetune_cycle)

                    mm = MemoryManager()
                    await asyncio.to_thread(mm.optimize_sqlite_database)
                    await asyncio.to_thread(mm.check_and_compile_milestone)
                    await asyncio.to_thread(mm.sync_to_ecosystem)
                    mm.enforce_memory_cap(max_ram_mb=200)

                print(f"[AUTONOMOUS LOOP] ✅ Iteration #{iteration} completed")
            except Exception as e:
                print(f"[AUTONOMOUS LOOP] ❌ Error in iteration #{iteration}: {e}")
            finally:
                _loop_is_busy = False
        await asyncio.sleep(8)  # wait 8s between iterations
    print("[AUTONOMOUS LOOP] ⏹️ Continuous Research Loop Stopped.")

@app.get("/evolution/status")
async def get_evolution_status():
    """Return live status of JAYA_RESEARCH -> JAYA_CORE Evolution Bridge."""
    return {
        "state": "running" if _is_autonomous_loop_running else ("idle" if not _latest_upgrade_result else "active"),
        "is_awake": True,
        "is_loop_running": _is_autonomous_loop_running,
        "loop_iteration_count": _loop_iteration_count,
        "latest_thought": "Continuous Autonomous Discovery Loop Active" if _is_autonomous_loop_running else "ResearchEcosystemBridge ready for autonomous upgrades",
        "latest_upgrade_result": _latest_upgrade_result,
        "timestamp": time.time()
    }

@app.get("/evolution/loop-status")
async def get_loop_status():
    """Check if continuous autonomous research loop is running."""
    return {
        "is_running": _is_autonomous_loop_running,
        "loop_iteration_count": _loop_iteration_count,
        "latest_upgrade": _latest_upgrade_result
    }

@app.get("/evolution/patches")
async def get_all_patches(limit: int = 50):
    """Read all applied JARVIS patches from agentic_jarvis.db SQLite database."""
    try:
        src_dir = Path(__file__).resolve().parent.parent
        db_path = src_dir.parent / "data" / "agentic_jarvis.db"
        if not db_path.exists():
            return {"patches": [], "total": 0, "db_exists": False}
        
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(str(db_path))
        conn.row_factory = _sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT patch_id, topic, statement, bayes_confidence, applied_at, patch_data "
                "FROM jarvis_patches ORDER BY applied_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            patches = []
            for row in rows:
                patch_data = {}
                try:
                    patch_data = json.loads(row["patch_data"] or "{}")
                except Exception:
                    pass
                patches.append({
                    "patch_id": row["patch_id"],
                    "topic": row["topic"],
                    "statement": row["statement"],
                    "bayes_confidence": row["bayes_confidence"],
                    "applied_at": row["applied_at"],
                    "novelty_score": patch_data.get("novelty_score", 0.0),
                    "target_system": patch_data.get("target_system", "JAYA_CORE_BRAIN"),
                    "llm_generated": patch_data.get("llm_generated", False),
                    "falsifiability": patch_data.get("falsifiability", ""),
                })
            count = conn.execute("SELECT COUNT(*) FROM jarvis_patches").fetchone()[0]
            return {"patches": patches, "total": count, "db_exists": True, "db_path": str(db_path)}
        finally:
            conn.close()
    except Exception as e:
        return {"patches": [], "total": 0, "db_exists": False, "error": str(e)}

@app.post("/evolution/start-autonomous-loop")
async def start_autonomous_loop():
    """Start continuous autonomous research loop."""
    global _is_autonomous_loop_running, _auto_loop_task
    if _is_autonomous_loop_running:
        return {"ok": True, "message": "Autonomous loop is already running", "is_running": True}
    
    _is_autonomous_loop_running = True
    _save_loop_state(True)  # Persist to SQLite
    _auto_loop_task = asyncio.create_task(_continuous_autonomous_research_worker())
    print("[API] ▶ Autonomous loop STARTED and state saved to DB.")
    return {"ok": True, "message": "Continuous Autonomous Research Loop Started", "is_running": True}

@app.post("/evolution/stop-autonomous-loop")
async def stop_autonomous_loop():
    """Stop continuous autonomous research loop."""
    global _is_autonomous_loop_running, _auto_loop_task
    _is_autonomous_loop_running = False
    _save_loop_state(False)  # Persist to SQLite
    if _auto_loop_task and not _auto_loop_task.done():
        try:
            _auto_loop_task.cancel()
        except Exception:
            pass
    print("[API] ⏹️ Autonomous loop STOPPED and state saved to DB.")
    return {"ok": True, "message": "Continuous Autonomous Research Loop Stopped", "is_running": False}

@app.post("/evolution/auto-upgrade")
async def trigger_auto_upgrade(custom_topic: Optional[str] = None):
    """Trigger autonomous research discovery and deployment to JAYA_CORE."""
    try:
        res = await asyncio.to_thread(_do_auto_upgrade_sync, custom_topic)
        return {
            "ok": True,
            "message": "Autonomous research loop executed & patch injected into JAYA_CORE (agentic_jarvis.db)",
            "result": res
        }
    except Exception as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(err))

@app.post("/evolution/auto-finetune")
async def trigger_auto_finetune():
    """Extract SFT dataset from agentic_jarvis.db and train LoRA neural weight adapter."""
    try:
        from auto_finetune import run_auto_finetune_cycle
        res = await asyncio.to_thread(run_auto_finetune_cycle)
        return {"ok": True, "message": "Autonomous LoRA Weight Fine-Tuning Executed", "result": res}
    except Exception as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(err))

@app.get("/evolution/adapters")
async def get_adapter_info():
    """Retrieve metadata about active LoRA neural weight adapters."""
    try:
        src_dir = Path(__file__).resolve().parent.parent
        meta_file = src_dir.parent / "data" / "adapters" / "adapter_metadata.json"
        if not meta_file.exists():
            return {"active_adapter": None, "exists": False}
        with open(meta_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"active_adapter": data, "exists": True}
    except Exception as err:
        return {"active_adapter": None, "exists": False, "error": str(err)}

@app.get("/evolution/memory-status")
async def get_memory_status():
    """Retrieve current RSS RAM memory footprint and milestone status."""
    try:
        from memory_manager import MemoryManager
        mm = MemoryManager()
        ram_info = mm.enforce_memory_cap(max_ram_mb=200)
        milestone_info = mm.check_and_compile_milestone()
        return {"ok": True, "ram": ram_info, "milestone": milestone_info}
    except Exception as err:
        return {"ok": False, "error": str(err)}

@app.post("/evolution/optimize-memory")
async def trigger_memory_optimization():
    """Optimize SQLite WAL indexes, enforce RAM garbage collection, and check milestone compilation."""
    try:
        from memory_manager import MemoryManager
        mm = MemoryManager()
        res_sqlite = await asyncio.to_thread(mm.optimize_sqlite_database)
        res_milestone = await asyncio.to_thread(mm.check_and_compile_milestone)
        res_ram = mm.enforce_memory_cap(max_ram_mb=200)
        return {
            "ok": True,
            "message": "Memory & Database Optimization Completed",
            "sqlite": res_sqlite,
            "milestone": res_milestone,
            "ram": res_ram
        }
    except Exception as err:
        raise HTTPException(status_code=500, detail=str(err))


def start():
    """Launch server"""
    uvicorn.run("network.research_api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
