# JAYA_AGENT — The Agent Framework (User-Facing Applications)

> **JAYA_AGENT** — Framework for building user-facing agents that use JAYA_CORE as their brain and JAYA_OS as their runtime.

---

## Purpose

JAYA_AGENT provides the **application layer** — the "apps" that users interact with. It bridges user intent (voice, text, UI) to JAYA_CORE's cognitive pipeline and JAYA_OS's execution environment.

```
┌─────────────────────────────────────────────────────────────────┐
│                      JAYA_AGENT (Apps)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Chat UI    │  │  Voice UI   │  │  Desktop UI │  ...         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    JAYA_CORE (Brain)                            │
│  IntentEngine → LinguaLogica → JayaIR → IronEngine             │
│  SpecGenerators: UI, Feature, Task, Action                     │
└─────────────────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      JAYA_OS (House)                            │
│  FeatureCompiler → FeatureRegistry → JayaBridge → IPC          │
│  WindowManager → Widget Runtime → Hardware                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Agent Types

| Agent Type | Description | Interface |
|---|---|---|
| **Chat Agent** | Text-based conversation | CLI, Web chat, Terminal |
| **Voice Agent** | Speech-to-text → Brain → Text-to-speech | Microphone + Speaker |
| **Desktop Agent** | Full desktop environment with dynamic UI | Window manager, widgets |
| **Embedded Agent** | Headless, API-driven | REST/gRPC, Webhooks |
| **Research Agent** | Autonomous research workflows | JAYA_RESEARCH integration |

---

## Core Components

### 1. Agent Runtime (`src/runtime/`)
- **AgentLoop** — Main event loop: perceive → reason → act
- **Perception** — Input adapters (text, voice, events, sensors)
- **Action Dispatcher** — Routes Brain specs to JAYA_OS
- **State Manager** — Conversation history, context, session persistence

### 2. Interface Adapters (`src/interfaces/`)
| Adapter | Input | Output |
|---|---|---|
| `TextInterface` | STDIN, WebSocket, REST | Text |
| `VoiceInterface` | Microphone (STT) | Audio (TTS) |
| `DesktopInterface` | Window events, clicks | UI Specs → JAYA_OS |
| `APIInterface` | HTTP/gRPC requests | JSON responses |

### 3. Skill/Plugin System (`src/skills/`)
- **Built-in Skills** — System control, file ops, web search, calculations
- **Custom Skills** — User-defined capabilities via spec generation
- **Skill Registry** — Discovery, versioning, dependency resolution

### 4. Memory Integration (`src/memory/`)
- **Short-term** — Conversation context (Brain's working memory)
- **Long-term** — RAG vault (rag_vault.db), episodic memory
- **Shared** — Cross-agent memory via JAYA_OS IPC

---

## Built-in Agents

### 1. Sovereign Chat (`agents/sovereign_chat/`)
```bash
# Minimal CLI chat with JAYA_CORE
python -m jaya_agent.sovereign_chat
```
- Direct brain_v2 conversation
- Intent learning (`learn "..."`)
- Benchmark commands

### 2. Voice Assistant (`agents/voice_assistant/`)
```bash
# Voice-driven JARVIS-like assistant
python -m jaya_agent.voice_assistant
```
- STT → IntentEngine → SpecGen → JAYA_OS → TTS
- Wake word detection
- Streaming responses

### 3. Desktop Shell (`agents/desktop_shell/`)
```bash
# Full dynamic desktop environment
python -m jaya_agent.desktop_shell
```
- Window manager integration
- Dynamic UI generation ("show me a dashboard")
- Feature mounting/unmounting at runtime

### 4. API Server (`agents/api_server/`)
```bash
# REST/gRPC endpoint for external integration
python -m jaya_agent.api_server
```
- `/chat` — Conversational endpoint
- `/intent` — Raw intent classification
- `/spec` — Generate specs (UI, Feature, Task)
- `/execute` — Mount & dispatch actions

---

## Development

### Creating a Custom Agent

```python
# my_agent.py
from jaya_agent.runtime import AgentLoop, TextInterface
from jaya_agent.skills import SkillRegistry

class MyAgent(AgentLoop):
    def __init__(self):
        super().__init__(
            interface=TextInterface(),
            skills=SkillRegistry.load_builtin()
        )
    
    async def on_user_input(self, text: str):
        # Custom pre-processing
        result = await super().on_user_input(text)
        # Custom post-processing
        return result

if __name__ == "__main__":
    MyAgent().run()
```

### Adding a Skill

```python
# skills/my_skill.py
from jaya_agent.skills import Skill, skill_action

class MySkill(Skill):
    name = "my_skill"
    description = "Custom capability"
    
    @skill_action("do_something", params={"target": "str"})
    async def do_something(self, target: str) -> str:
        # Can emit specs for JAYA_OS
        return f"Did something with {target}"

# Register
SkillRegistry.register(MySkill)
```

---

## Configuration

```yaml
# config/agent.yaml
agent:
  name: "JAYA"
  personality: "helpful, concise, proactive"
  
interfaces:
  text:
    enabled: true
    prompt: "> "
  voice:
    enabled: false
    wake_word: "hey jaya"
    stt_model: "whisper-base"
    tts_voice: "en-US-Neural"
  desktop:
    enabled: false
    
brain:
  model_path: "models/jaya-brain.gguf"
  offline_mode: true
  
os:
  features_dir: "./features"
  max_mounted_features: 50
  
memory:
  rag_vault: "../rag_vault.db"
  session_db: "./sessions.sqlite"
  max_context_tokens: 4096
```

---

## Roadmap

| Phase | Focus | Deliverables |
|---|---|---|
| **A-1** | Agent Runtime Core | AgentLoop, TextInterface, SkillRegistry |
| **A-2** | Voice Interface | STT/TTS integration, wake word, streaming |
| **A-3** | Desktop Shell | WindowManager integration, dynamic UI |
| **A-4** | API Server | REST/gRPC, auth, rate limiting |
| **A-5** | Multi-Agent | Agent-to-agent comms, shared memory |
| **A-6** | Plugin Ecosystem | Skill marketplace, sandboxed plugins |

---

## 🔗 Related

- [JAYA_CORE](../JAYA_CORE/README.md) — The Brain (cognitive core)
- [JAYA_OS](../JAYA_OS/README.md) — The House (execution environment)
- [JAYA_RESEARCH](../JAYA_RESEARCH/README.md) — Research Assistant (cloud-powered)
- [Root Architecture](../docs/arsitektur_utama_jaya.md) — 40 Pillars, Dual Domain