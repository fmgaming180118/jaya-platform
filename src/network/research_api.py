"""
JAYA Research API Server (FastAPI)
The backbone of the Research UI.
"""
from contextlib import asynccontextmanager
from typing import List, Optional
import asyncio
import sys
import os
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research.agent import ResearchAgent
from research.enhanced_rag import EnhancedRAGClient, VectorStore
from research.graph_rag import GraphRAGEngine
from research.meta_analysis import MetaAnalyst
from network.api_models import ResearchRequest, ChatRequest, VideoIngestRequest, DebateRequest
from research.debate_agent import DebateAgent
from research.video_processor import VideoProcessor
from research.workspace_manager import WorkspaceManager
from research.academic.reviewer import ReviewerAgent
from research.academic.tracker import ExperimentTracker
import traceback
from fastapi.responses import FileResponse
from evolution.twin import DigitalTwin

# Global Managers
workspace_manager = WorkspaceManager()
active_sessions = {} # workspace_id -> {rag, graph}
digital_twin = DigitalTwin()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[API] Starting JAYA Research Backend...")
    # Start the Digital Twin in background
    asyncio.create_task(digital_twin.start_loop())
    yield
    # Shutdown
    print("[API] Shutting down...")
    digital_twin.stop()

app = FastAPI(title="JAYA Research API", version="2.0", lifespan=lifespan)

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
        paths = workspace_manager.get_paths(workspace_id)
        
        # Initialize engines with specific paths
        rag = EnhancedRAGClient(vector_store_path=paths['vector_store'])
        graph = GraphRAGEngine(storage_path=paths['knowledge_graph'])
        
        active_sessions[workspace_id] = {
            "rag": rag,
            "graph": graph
        }
    
    return active_sessions[workspace_id]["rag"], active_sessions[workspace_id]["graph"]

# Pre-load default
get_engines("default")

@app.get("/")
def health_check():
    return {"status": "online", "service": "JAYA Research API"}

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
    reviewer = ReviewerAgent()
    questions = reviewer.generate_defense_questions(topic, abstract)
    return {"topic": topic, "questions": questions}

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
    success = digital_twin.set_mode(mode)
    if not success:
#        raise HTTPException(status_code=400, detail="Invalid mode. Use 'thesis' or 'exploration'.")
        return {"status": "error", "message": "Invalid mode"}
    return {"status": "success", "mode": digital_twin.mode.value}

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
    
    # 4. Synthesize with Teacher
    from teacher import Teacher
    # Use 'reasoning' for deep synthesis, or 'chat' for faster response?
    # Let's use 'reasoning' for high quality RAG synthesis
    teacher = Teacher(model_type="reasoning")
    
    prompt = f"""
    Context: 
    {full_context}
    
    User Question: {request.message}
    
    Answer based on the combined context (Vector + Graph):
    """
    answer = teacher.suggest_optimization(prompt, focus="Research Chat")
    
    return {
        "answer": answer,
        "sources": [r['document'].get('file_name', 'Unknown') for r in results_vector] + ["Knowledge Graph"]
    }

@app.post("/ingest/video")
async def ingest_video(request: VideoIngestRequest, background_tasks: BackgroundTasks):
    """
    Ingest Youtube video using AI-Q Video Analysis Logic
    """
    from research.video_processor import VideoProcessor
    
    def process(url):
        processor = VideoProcessor()
        result = processor.process_video(url)
        
        # Store in Memory
        from memory import DiscoveryMemory
        memory = DiscoveryMemory("data/evolution_memory.json")
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

@app.get("/evolution/status")
async def get_evolution_status():
    """Get the current state of the Digital Twin"""
    recent_thoughts = digital_twin.memory.get_recent_thoughts(limit=5)
    return {
        "state": digital_twin.state.value,
        "is_awake": digital_twin.running,
        "latest_thought": recent_thoughts[-1] if recent_thoughts else None,
        "recent_history": recent_thoughts
    }

@app.get("/evolution/logs")
async def get_evolution_logs(limit: int = 50):
    """Get full history of Twin's thoughts"""
    return digital_twin.memory.get_recent_thoughts(limit=limit)

@app.post("/evolution/night_mode")
def set_night_mode(enabled: bool):
    digital_twin.toggle_night_mode(enabled)
    return {"status": "success", "night_mode": enabled}

@app.get("/history")
def get_history():
    """Get past research reports"""
    return meta_analyst.get_research_history()

def start():
    """Launch server"""
    uvicorn.run("network.research_api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    import uvicorn
    # Use environment variable for port or default to 8000
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
