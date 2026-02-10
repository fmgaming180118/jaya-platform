"""
JAYA Research API Server (FastAPI)
The backbone of the Research UI.
"""
import sys
import os
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research.agent import ResearchAgent
from research.enhanced_rag import EnhancedRAGClient
from research.meta_analysis import MetaAnalyst
from network.api_models import ResearchRequest, ChatRequest, VideoIngestRequest, DebateRequest

app = FastAPI(title="JAYA Research API", version="1.0.0")

# CORS for Vite Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
rag_client = EnhancedRAGClient()
meta_analyst = MetaAnalyst()

# Initialize Graph Engine
from research.graph_rag import GraphRAGEngine
graph_engine = GraphRAGEngine()

@app.get("/")
def health_check():
    return {"status": "online", "service": "JAYA Research API"}

@app.post("/research/autonomous")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Start autonomous research in background"""
    def run_agent(topic, focus):
        agent = ResearchAgent(topic=topic, focus_areas=focus)
        report = agent.run(human_in_loop=False) # Auto mode
        
        # Ingest into Graph
        print(f"[API] Ingesting report into Knowledge Graph...")
        graph_engine.ingest_document(report, f"Research: {topic}")
        
        print(f"[API] Research completed for: {topic}")
        
    background_tasks.add_task(run_agent, request.topic, request.focus_areas)
    return {"message": "Research started", "topic": request.topic}

@app.post("/chat")
async def chat_with_knowledge(request: ChatRequest):
    """Chat coupled with RAG + Graph"""
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
    teacher = Teacher()
    
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
def get_knowledge_graph():
    """Get knowledge graph for visualization"""
    try:
        return graph_engine.get_viz_data()
    except Exception as e:
        print(f"Graph Error: {e}")
        return {"nodes": [], "edges": []}

@app.get("/history")
def get_history():
    """Get past research reports"""
    return meta_analyst.get_research_history()

def start():
    """Launch server"""
    uvicorn.run("network.research_api:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start()
