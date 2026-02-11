"""
Jaya Voice Agent using Nimble Pipecat Framework
"""
import os
import sys
import threading
import time
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JayaVoice")

# Ensure we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
try:
    from research.enhanced_rag import EnhancedRAGClient
except ImportError:
    logger.warning("[Voice] Could not import EnhancedRAGClient. RAG features disabled.")
    EnhancedRAGClient = None

class JayaVoiceAgent(threading.Thread):
    def __init__(self, api_key=None, rag_client=None):
        super().__init__()
        self.running = False
        self.loop = None
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self._stop_event = threading.Event()
        
        # Initialize RAG Client
        self.rag_client = rag_client
        if self.rag_client is None and EnhancedRAGClient:
            try:
                self.rag_client = EnhancedRAGClient()
                logger.info("[Voice] RAG Client initialized successfully.")
            except Exception as e:
                logger.error(f"[Voice] Failed to init RAG Client: {e}")

    def run(self):
        """Thread main loop"""
        self.running = True
        logger.info("[Voice] Agent Process Started")
        
        # Create a new event loop for this thread (asyncio is required for Pipecat)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self._run_pipecat_pipeline())
        except Exception as e:
            logger.error(f"[Voice] Error in pipeline: {e}")
        finally:
            self.running = False
            logger.info("[Voice] Agent Stopped")

    def stop(self):
        """Signal the agent to stop"""
        self._stop_event.set()
        self.running = False

    async def _run_pipecat_pipeline(self):
        """
        Main Async Pipeline using Pipecat.
        Simulated logic if libraries are missing to prevent crash.
        """
        try:
            # Try importing Pipecat components
            # Note: These imports might fail if pip install pipecat-ai is not run
            from pipecat.pipeline.pipeline import Pipeline
            from pipecat.pipeline.task import PipelineTask
            # from pipecat.frames.context import OpenAILLMContext # Removed for pure NVIDIA stack
            # We would use NvidiaRivaSTT, NvidiaLlamaLLM, NvidiaRivaTTS here
            # For blueprint purposes, we assume these classes exist or utilize standard ones
            
            logger.info("[Voice] Pipecat libraries found. Initializing NIM services...")
            
            # --- Placeholder for Actual Pipeline Construction ---
            # 1. Transport (Local Audio)
            # transport = LocalAudioTransport()
            
            # 2. Services (NIM)
            # stt = NvidiaRivaSTT(api_key=self.api_key)
            # llm = NvidiaLlamaLLM(api_key=self.api_key)
            # tts = NvidiaRivaTTS(api_key=self.api_key)
            
            # 3. Task
            # task = PipelineTask(transport, Pipeline([stt, llm, tts]))
            
            # 4. Run checking for 'Jaya' wake word manually or via VAD
            logger.info("[Voice] Listening for 'Jaya'...")
            
            while not self._stop_event.is_set():
                # Simulation loop to keep thread alive without consuming 100% CPU
                # In a real Pipecat loop, this would be event-driven by the pipeline runner
                await asyncio.sleep(1)
                
        except ImportError:
            logger.warning("[Voice] 'pipecat-ai' not installed. Running in Mock Mode.")
            logger.warning("[Voice] Please run: pip install pipecat-ai")
            
            # Mock Loop with Console Interaction for testing RAG
            logger.info("[Voice] Mock Mode: Type in console to simulate voice input (or wait)")
            
            while not self._stop_event.is_set():
                # For demonstration, we just sleep. 
                # In a real integration, we'd hook into audio stream.
                # To verify RAG, we can simulate a query occasionally or just wait.
                time.sleep(2)

    def process_query(self, text):
        """
        Process a text query using RAG and LLM (Simulation helper).
        """
        logger.info(f"[Voice] Processing query: '{text}'")
        
        context = ""
        if self.rag_client:
            # Query RAG
            results = self.rag_client.query(text)
            # Assuming query returns a string or list of docs
            if isinstance(results, dict) and "answer" in results:
                 context = results["answer"] # If RAG returns a generated answer
            elif isinstance(results, list): # If returns chunks
                 context = "\n".join([doc.get('content', '') for doc in results[:2]])
            
            logger.info(f"[Voice] Retrieved Context: {context[:100]}...")
        
        # Here we would send (System Prompt + Context + User Query) to LLM
        return f"Response based on context: {context[:500]}..."

if __name__ == "__main__":
    # Test stub
    agent = JayaVoiceAgent()
    agent.start()
    time.sleep(5)
    agent.stop()
    agent.join()
