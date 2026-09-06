"""
CLI/REPL Interface for JAYA_CORE.

Provides:
- Interactive REPL for JAYA
- Command-line interface for common operations
- Script execution
- Configuration management
- Debugging and inspection tools
"""

from __future__ import annotations

import asyncio
import cmd
import json
import logging
import os
import readline
import shlex
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from jaya_core.observability import get_structured_logger, init_observability
from jaya_core.ai_connectors import create_cognitive_adapter_from_env
from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.memory.episodic import EpisodicMemoryStore, MemoryEvent
from jaya_core.memory.working import WorkingMemory
from jaya_core.cognitive.context import ContextManager
from jaya_core.resources.profiler import ResourceProfiler
from jaya_core.identity.models import NodeIdentity, NodeClass
from jaya_core.agents import get_agent_registry, create_local_agent, delegate_task
from jaya_core.sandbox import get_python_sandbox, get_javascript_sandbox
from jaya_core.multimodal import get_multimodal_adapter, MultiModalContent, ModalityType
from jaya_core.rag import get_rag_pipeline, Document

logger = get_structured_logger(__name__, component="cli")


# ============================================================================
# JAYA REPL
# ============================================================================

class JayaREPL(cmd.Cmd):
    """Interactive REPL for JAYA."""
    
    intro = """
╔══════════════════════════════════════════════════════════════╗
║                    JAYA Interactive REPL                      ║
║              Type 'help' for commands, 'exit' to quit        ║
╚══════════════════════════════════════════════════════════════╝
"""
    prompt = "jaya> "
    
    def __init__(self):
        super().__init__()
        self.engine: Optional[IronEngine] = None
        self.cognitive_adapter = None
        self.episodic_memory: Optional[EpisodicMemoryStore] = None
        self.working_memory: Optional[WorkingMemory] = None
        self.context_manager = ContextManager()
        self.multimodal_adapter = None
        self.rag_pipeline = None
        self.python_sandbox = None
        self.js_sandbox = None
        self._initialized = False
    
    def _initialize(self):
        """Lazy initialization."""
        if self._initialized:
            return
        
        try:
            # Initialize observability
            init_observability(
                service_name="jaya-cli",
                log_level=logging.WARNING,  # Quiet for REPL
                json_logs=False,
            )
            
            # Initialize IronEngine
            self.engine = IronEngine(
                model_path="missing.jay",
                password="x",
                enable_twin=False,
            )
            self.engine.ignite()
            
            # Initialize cognitive adapter
            self.cognitive_adapter = create_cognitive_adapter_from_env()
            
            # Initialize memory
            self.episodic_memory = EpisodicMemoryStore(db_path=":memory:")
            self.working_memory = WorkingMemory(session_id="repl_session")
            
            # Initialize multimodal
            self.multimodal_adapter = get_multimodal_adapter(self.cognitive_adapter)
            
            # Initialize RAG
            self.rag_pipeline = get_rag_pipeline()
            
            # Initialize sandboxes
            self.python_sandbox = get_python_sandbox()
            self.js_sandbox = get_javascript_sandbox()
            
            self._initialized = True
            logger.info("REPL initialized")
            
        except Exception as e:
            logger.error("REPL initialization failed", error=str(e))
            print(f"Warning: Some features may not be available: {e}")
    
    # --- Core Commands ---
    
    def do_chat(self, arg: str):
        """Chat with JAYA: chat <message>"""
        if not arg:
            print("Usage: chat <message>")
            return
        
        self._initialize()
        
        try:
            # Use cognitive adapter for chat
            response = self.cognitive_adapter.generate(arg)
            print(f"JAYA: {response.text}")
            print(f"  [Source: {response.source}, Model: {response.model_used}, Confidence: {response.confidence:.2f}]")
            
            # Store in memory
            self.working_memory.set(f"chat_{time.time()}", {"user": arg, "assistant": response.text})
            
        except Exception as e:
            print(f"Error: {e}")
    
    def do_cognitive(self, arg: str):
        """Cognitive reasoning: cognitive <prompt> [--local] [--context key=value]"""
        if not arg:
            print("Usage: cognitive <prompt> [--local] [--context key=value]")
            return
        
        self._initialize()
        
        # Parse arguments
        parts = shlex.split(arg)
        prompt_parts = []
        context = {}
        force_local = False
        
        i = 0
        while i < len(parts):
            if parts[i] == "--local":
                force_local = True
            elif parts[i] == "--context" and i + 1 < len(parts):
                kv = parts[i + 1].split("=", 1)
                if len(kv) == 2:
                    context[kv[0]] = kv[1]
                i += 1
            else:
                prompt_parts.append(parts[i])
            i += 1
        
        prompt = " ".join(prompt_parts)
        
        try:
            response = self.cognitive_adapter.generate(
                prompt=prompt,
                context=context if context else None,
                force_local=force_local,
            )
            print(f"JAYA: {response.text}")
            print(f"  [Source: {response.source}, Model: {response.model_used}, Confidence: {response.confidence:.2f}]")
            if response.metadata:
                print(f"  Metadata: {json.dumps(response.metadata, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
    
    def do_intent(self, arg: str):
        """Execute intent through IronEngine: intent <command>"""
        if not arg:
            print("Usage: intent <command>")
            return
        
        self._initialize()
        
        try:
            result = self.engine.execute_intent(arg)
            print(f"Result: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")
    
    # --- Memory Commands ---
    
    def do_memory(self, arg: str):
        """Memory operations: memory <store|recall|list|clear> [args]"""
        if not arg:
            print("Usage: memory <store|recall|list|clear> [args]")
            return
        
        self._initialize()
        parts = shlex.split(arg)
        subcmd = parts[0]
        
        if subcmd == "store":
            if len(parts) < 3:
                print("Usage: memory store <key> <value>")
                return
            key = parts[1]
            value = " ".join(parts[2:])
            self.working_memory.set(key, value)
            print(f"Stored: {key} = {value}")
        
        elif subcmd == "recall":
            if len(parts) < 2:
                print("Usage: memory recall <key>")
                return
            key = parts[1]
            value = self.working_memory.get(key)
            if value is not None:
                print(f"{key} = {value}")
            else:
                print(f"Key not found: {key}")
        
        elif subcmd == "list":
            # WorkingMemory doesn't have list method, show info
            print("Working memory session:", self.working_memory.session_id)
        
        elif subcmd == "clear":
            self.working_memory = WorkingMemory(session_id="repl_session")
            print("Working memory cleared")
        
        else:
            print(f"Unknown subcommand: {subcmd}")
    
    def do_episodic(self, arg: str):
        """Episodic memory: episodic <store|recall|search> [args]"""
        if not arg:
            print("Usage: episodic <store|recall|search> [args]")
            return
        
        self._initialize()
        parts = shlex.split(arg)
        subcmd = parts[0]
        
        if subcmd == "store":
            if len(parts) < 4:
                print("Usage: episodic store <session_id> <goal_id> <payload_json>")
                return
            session_id = parts[1]
            goal_id = parts[2]
            payload = json.loads(" ".join(parts[3:]))
            
            event = MemoryEvent(
                event_id=f"evt_{time.time()}",
                event_type="USER_STORE",
                session_id=session_id,
                goal_id=goal_id,
                payload=payload,
                node_id="repl",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                sequence_number=0,
            )
            self.episodic_memory.append_event(event)
            print("Event stored")
        
        elif subcmd == "recall":
            if len(parts) < 2:
                print("Usage: episodic recall <session_id> [limit]")
                return
            session_id = parts[1]
            limit = int(parts[2]) if len(parts) > 2 else 10
            events = self.episodic_memory.query_by_session(session_id, limit=limit)
            for e in events:
                print(f"  [{e.sequence_number}] {e.event_type}: {json.dumps(e.payload)}")
        
        elif subcmd == "search":
            if len(parts) < 2:
                print("Usage: episodic search <goal_id> [limit]")
                return
            goal_id = parts[1]
            limit = int(parts[2]) if len(parts) > 2 else 10
            events = self.episodic_memory.query_by_goal(goal_id, limit=limit)
            for e in events:
                print(f"  [{e.sequence_number}] {e.event_type}: {json.dumps(e.payload)}")
        
        else:
            print(f"Unknown subcommand: {subcmd}")
    
    # --- RAG Commands ---
    
    def do_rag(self, arg: str):
        """RAG operations: rag <add|search|context> [args]"""
        if not arg:
            print("Usage: rag <add|search|context> [args]")
            return
        
        self._initialize()
        parts = shlex.split(arg)
        subcmd = parts[0]
        
        if subcmd == "add":
            if len(parts) < 3:
                print("Usage: rag add <doc_id> <content> [metadata_json]")
                return
            doc_id = parts[1]
            content = parts[2]
            metadata = json.loads(parts[3]) if len(parts) > 3 else {}
            
            doc = Document(id=doc_id, content=content, metadata=metadata)
            self.rag_pipeline.add_document(doc)
            print(f"Document added: {doc_id}")
        
        elif subcmd == "search":
            if len(parts) < 2:
                print("Usage: rag search <query> [top_k]")
                return
            query = parts[1]
            top_k = int(parts[2]) if len(parts) > 2 else 5
            
            results = self.rag_pipeline.retrieve(query, top_k=top_k)
            for r in results:
                print(f"  [{r.rank}] Score: {r.score:.3f} - {r.document.id}: {r.document.content[:100]}...")
        
        elif subcmd == "context":
            if len(parts) < 2:
                print("Usage: rag context <query> [max_tokens]")
                return
            query = parts[1]
            max_tokens = int(parts[2]) if len(parts) > 2 else 2000
            
            context = self.rag_pipeline.generate_context(query, max_tokens=max_tokens)
            print(context)
        
        else:
            print(f"Unknown subcommand: {subcmd}")
    
    # --- Sandbox Commands ---
    
    def do_python(self, arg: str):
        """Execute Python code: python <code> [--packages pkg1,pkg2] [--timeout N]"""
        if not arg:
            print("Usage: python <code> [--packages pkg1,pkg2] [--timeout N]")
            return
        
        self._initialize()
        
        # Parse
        parts = shlex.split(arg)
        code_parts = []
        packages = []
        timeout = 30.0
        
        i = 0
        while i < len(parts):
            if parts[i] == "--packages" and i + 1 < len(parts):
                packages = parts[i + 1].split(",")
                i += 1
            elif parts[i] == "--timeout" and i + 1 < len(parts):
                timeout = float(parts[i + 1])
                i += 1
            else:
                code_parts.append(parts[i])
            i += 1
        
        code = " ".join(code_parts)
        
        async def run():
            result = await self.python_sandbox.execute(
                code=code,
                packages=packages if packages else None,
                timeout=timeout,
            )
            return result
        
        result = asyncio.run(run())
        
        print(f"Status: {result.status.value}")
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        print(f"Duration: {result.duration_ms:.1f}ms")
    
    def do_js(self, arg: str):
        """Execute JavaScript code: js <code> [--timeout N]"""
        if not arg:
            print("Usage: js <code> [--timeout N]")
            return
        
        self._initialize()
        
        parts = shlex.split(arg)
        code_parts = []
        timeout = 30.0
        
        i = 0
        while i < len(parts):
            if parts[i] == "--timeout" and i + 1 < len(parts):
                timeout = float(parts[i + 1])
                i += 1
            else:
                code_parts.append(parts[i])
            i += 1
        
        code = " ".join(code_parts)
        
        async def run():
            result = await self.js_sandbox.execute(
                code=code,
                timeout=timeout,
            )
            return result
        
        result = asyncio.run(run())
        
        print(f"Status: {result.status.value}")
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        print(f"Duration: {result.duration_ms:.1f}ms")
    
    # --- Multimodal Commands ---
    
    def do_vision(self, arg: str):
        """Vision processing: vision <image_path> [prompt]"""
        if not arg:
            print("Usage: vision <image_path> [prompt]")
            return
        
        self._initialize()
        
        parts = shlex.split(arg)
        image_path = parts[0]
        prompt = " ".join(parts[1:]) if len(parts) > 1 else "Describe this image."
        
        if not os.path.exists(image_path):
            print(f"File not found: {image_path}")
            return
        
        content = MultiModalContent.from_file(image_path)
        
        async def run():
            result = await self.multimodal_adapter.generate_with_vision(
                prompt=prompt,
                images=[content],
            )
            return result
        
        result = asyncio.run(run())
        print(f"Vision: {result.get('text', 'No response')}")
        if result.get('vision_context'):
            print(f"Context: {result['vision_context']}")
    
    def do_audio(self, arg: str):
        """Audio processing: audio <audio_path>"""
        if not arg:
            print("Usage: audio <audio_path>")
            return
        
        self._initialize()
        
        audio_path = arg.strip()
        if not os.path.exists(audio_path):
            print(f"File not found: {audio_path}")
            return
        
        content = MultiModalContent.from_file(audio_path)
        
        async def run():
            result = await self.multimodal_adapter.generate_with_audio(
                prompt="Transcribe this audio.",
                audio=content,
            )
            return result
        
        result = asyncio.run(run())
        print(f"Transcript: {result.get('text', 'No response')}")
        if result.get('audio_transcript'):
            print(f"Raw: {result['audio_transcript']}")
    
    # --- Agent Commands ---
    
    def do_agent(self, arg: str):
        """Agent operations: agent <create|delegate|list> [args]"""
        if not arg:
            print("Usage: agent <create|delegate|list> [args]")
            return
        
        self._initialize()
        parts = shlex.split(arg)
        subcmd = parts[0]
        
        if subcmd == "create":
            if len(parts) < 4:
                print("Usage: agent create <agent_id> <name> <capability> [description]")
                return
            agent_id = parts[1]
            name = parts[2]
            capability = parts[3]
            description = " ".join(parts[4:]) if len(parts) > 4 else ""
            
            async def run():
                def executor(data):
                    return {"echo": data}
                
                agent = await create_local_agent(agent_id, name, capability, executor, description)
                return agent
            
            agent = asyncio.run(run())
            print(f"Agent created: {agent.agent_id} ({agent.name})")
        
        elif subcmd == "delegate":
            if len(parts) < 3:
                print("Usage: agent delegate <capability> <input_json> [priority]")
                return
            capability = parts[1]
            input_data = json.loads(parts[2])
            priority = int(parts[3]) if len(parts) > 3 else 0
            
            async def run():
                result = await delegate_task(capability, input_data, priority)
                return result
            
            result = asyncio.run(run())
            print(f"Result: {json.dumps(result, indent=2)}")
        
        elif subcmd == "list":
            async def run():
                registry = get_agent_registry()
                agents = await registry.list_agents()
                return agents
            
            agents = asyncio.run(run())
            for a in agents:
                print(f"  {a.agent_id}: {a.name} ({a.status.value}) - {len(a.capabilities)} capabilities")
        
        else:
            print(f"Unknown subcommand: {subcmd}")
    
    # --- System Commands ---
    
    def do_status(self, arg: str):
        """Show system status"""
        self._initialize()
        
        print("=== JAYA System Status ===")
        
        # Engine status
        if self.engine:
            status = self.engine.status()
            print(f"\nIronEngine:")
            print(f"  Initialized: {status.get('initialized', False)}")
            print(f"  Narrative events: {status.get('narrative', {}).get('events', 0)}")
        
        # Cognitive adapter status
        if self.cognitive_adapter:
            cad_status = self.cognitive_adapter.get_status()
            print(f"\nCognitive Adapter:")
            print(f"  Local LLM: {cad_status['local_llm']['available']}")
            print(f"  Cloud LLM: {cad_status['cloud_llm']['available']}")
            print(f"  Providers: {list(cad_status['cloud_llm']['providers'].keys())}")
        
        # Memory status
        print(f"\nMemory:")
        print(f"  Working memory session: {self.working_memory.session_id}")
        
        # Resource status
        profiler = ResourceProfiler()
        profile = profiler.profile()
        print(f"\nResources:")
        print(f"  CPU: {profile.cpu_percent:.1f}%")
        print(f"  Memory: {profile.process_memory_mb:.1f} MB")
        print(f"  Node class: {profile.node_class.value}")
    
    def do_config(self, arg: str):
        """Configuration: config <show|set|get> [key] [value]"""
        if not arg:
            print("Usage: config <show|set|get> [key] [value]")
            return
        
        parts = shlex.split(arg)
        subcmd = parts[0]
        
        if subcmd == "show":
            # Show environment config
            jaya_vars = {k: v for k, v in os.environ.items() if k.startswith("JAYA_")}
            for k, v in sorted(jaya_vars.items()):
                # Mask sensitive values
                if any(s in k.lower() for s in ["key", "secret", "password", "token"]):
                    v = "***MASKED***"
                print(f"  {k}={v}")
        
        elif subcmd == "get":
            if len(parts) < 2:
                print("Usage: config get <key>")
                return
            key = parts[1]
            value = os.environ.get(key, "NOT SET")
            print(f"{key}={value}")
        
        elif subcmd == "set":
            if len(parts) < 3:
                print("Usage: config set <key> <value>")
                return
            key = parts[1]
            value = " ".join(parts[2:])
            os.environ[key] = value
            print(f"Set {key}={value} (session only)")
        
        else:
            print(f"Unknown subcommand: {subcmd}")
    
    def do_history(self, arg: str):
        """Show command history"""
        for i in range(readline.get_current_history_length()):
            print(f"  {i+1}: {readline.get_history_item(i+1)}")
    
    def do_clear(self, arg: str):
        """Clear screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def do_exit(self, arg: str):
        """Exit REPL"""
        print("Goodbye!")
        return True
    
    def do_quit(self, arg: str):
        """Exit REPL"""
        return self.do_exit(arg)
    
    def do_EOF(self, arg: str):
        """Exit on Ctrl+D"""
        print()
        return True
    
    def emptyline(self):
        """Do nothing on empty line"""
        pass
    
    def default(self, line: str):
        """Default: treat as chat"""
        if line.strip():
            self.do_chat(line)


# ============================================================================
# CLI Entry Point
# ============================================================================

def create_cli() -> JayaREPL:
    """Create CLI instance."""
    return JayaREPL()


def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="JAYA CLI")
    parser.add_argument("-c", "--command", help="Execute single command and exit")
    parser.add_argument("--no-repl", action="store_true", help="Don't start REPL")
    parser.add_argument("--config", help="Config file path")
    
    args = parser.parse_args()
    
    repl = create_cli()
    
    if args.command:
        # Execute single command
        repl._initialize()
        repl.onecmd(args.command)
    elif not args.no_repl:
        # Start REPL
        repl.cmdloop()


if __name__ == "__main__":
    main()