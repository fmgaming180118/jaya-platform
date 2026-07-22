# Phase 4: Proactive Intelligence

## Objective
Implement **anticipatory, autonomous intelligence** — enabling JAYA to act proactively, reason speculatively, maintain narrative coherence, and collaborate with peer instances — the hallmark of a true JARVIS-like assistant.

---

## Scope
- **In scope**: 8 proactive pillars (3, 6, 7, 27, 30, 31, 32, 36, 38, 39, 40), ProactiveLoop integration
- **Out of scope**: Core reasoning pipeline (Phase 1), self-upgrade (Phase 2), spec generation (Phase 3)

---

## Deliverables

| # | Deliverable | Pillar | File | Status |
|---|---|---|---|---|
| 1 | SpontaneityEngine | 3, 6 | `src/brain_v2/engine/spontaneity.py` | 📋 Planned |
| 2 | SpeculativeReasoner | 36 | `src/brain_v2/engine/speculative.py` | 📋 Planned |
| 3 | MetaCognitivePlanner | 38 | `src/brain_v2/extensions/twin/meta_planner.py` | 📋 Planned |
| 4 | NarrativeContinuity | 31 | `src/brain_v2/soul/narrative.py` | 📋 Planned |
| 5 | CollectivePulse | 32 | `src/brain_v2/engine/collective_pulse.py` | 📋 Planned |
| 6 | DynamicObjective | 39 | `src/brain_v2/soul/dynamic_objective.py` | 📋 Planned |
| 7 | IntentExtrapolator | 40 | `src/brain_v2/engine/intent_extrapolation.py` | 📋 Planned |
| 8 | ProactiveLoop | — | `src/brain_v2/engine/proactive_loop.py` | 📋 Planned |
| 9 | TemporalWeighting integration | 27 | `src/brain_v2/soul/temporal_memory.py` | ✅ Partial |
| 10 | CognitiveSilence integration | 7 | `src/brain_v2/engine/runtime.py` | ✅ Done |
| 11 | Phase 4 integration tests | — | `tests/test_phase4_proactive.py` | 📋 Planned |

---

## Pillar Implementations

### Pillar 3: Active Dreaming
**Idle-time simulation & hypothesis generation**
```python
class ActiveDreaming:
    def __init__(self, engine: IronEngine):
        self.engine = engine
        self.dream_interval = 300  # 5 min idle
    
    def on_idle(self, idle_duration: float):
        if idle_duration > self.dream_interval:
            self._dream()
    
    def _dream(self):
        # Sample diverse memories
        memories = self.engine.memory.sample(k=10, strategy="diverse")
        # Find knowledge gaps
        gaps = self._find_gaps(memories)
        # Generate hypotheses
        for gap in gaps:
            hypo = self._generate_hypothesis(gap)
            if self.engine.ethical_heart.is_safe(hypo):
                self.engine.task_queue.enqueue(VerifyHypothesis(hypo), Priority.LOW)
```

### Pillar 6: Stochastic Spontaneity
**Entropy-driven exploration**
```python
class StochasticSpontaneity:
    def __init__(self, entropy_source: EntropySource):
        self.entropy = entropy_source
        self.rate = 0.01  # 1% per idle cycle
    
    def maybe_act(self, context: Context) -> Optional[Action]:
        if self.entropy.random() < self.rate:
            return self._propose_action(context)
        return None
```

### Pillar 7: Cognitive Silence ✅ DONE
**Resource-aware pausing** — Integrated in IronEngine via ResourceMonitor

### Pillar 27: Temporal Weighting ✅ PARTIAL
**Time-decay relevance** — Implemented in temporal_memory.py

### Pillar 30: Twin Protocol
**Multi-node synchronization**
```python
class TwinProtocol:
    def __init__(self, engine: IronEngine, network: P2PNetwork):
        self.engine = engine
        self.network = network
    
    def sync_identity(self, peer: Peer) -> bool:
        # Verify DNA anchor match
        # Sync narrative continuity
        # Sync learned patterns (not private data)
        ...
```

### Pillar 31: Narrative Continuity
**Autobiographical coherence**
```python
class NarrativeContinuity:
    def record(self, event: str, content: Dict):
        entry = NarrativeEntry(timestamp=now(), event=event, content=content)
        self.storage.append(entry)
    
    def generate_daily_summary(self) -> str:
        # Synthesize day's events into coherent narrative
        # Store as consolidated memory
        ...
    
    def get_life_story(self, query: str) -> str:
        # Answer questions about past decisions
        ...
```

### Pillar 32: Collective Pulse
**Federated algorithmic discovery (ZK-proof)**
```python
class CollectivePulse:
    def share_discovery(self, discovery: AlgorithmicDiscovery):
        zk_proof = self._create_zk_proof(discovery)
        for peer in self.network.trusted_peers():
            peer.send(CollectiveMessage(type="discovery", payload=discovery, zk_proof=zk_proof))
    
    def receive_discovery(self, message: CollectiveMessage):
        if self._verify_zk_proof(message.zk_proof):
            candidate = self._reconstruct(message.payload)
            if self.engine.evolution_gate.evaluate(candidate).promoted:
                self.engine.deploy_candidate(candidate)
```

### Pillar 36: Speculative Reasoning
**Multi-scenario foresight**
```python
class SpeculativeReasoner:
    def simulate(self, state: State, action: Action) -> List[Scenario]:
        scenarios = []
        for _ in range(self.max_scenarios):
            variant = self._perturb_state(state)
            trace = self._simulate_trace(variant, action, depth=self.max_depth)
            scenarios.append(Scenario(action, trace))
        return sorted(scenarios, key=lambda s: s.expected_value, reverse=True)
```

### Pillar 38: Meta-Cognitive Planning
**Strategy evaluation before action**
```python
class MetaCognitivePlanner:
    def plan_with_reflection(self, goal: Goal) -> Plan:
        plan = self.engine.task_planner.plan(goal)
        critique = self._critique_plan(plan)
        if critique.needs_revision:
            plan = self._revise_plan(plan, critique)
        self.engine.narrative.record("meta_planning", {"goal": goal, "plan": plan, "critique": critique})
        return plan
```

### Pillar 39: Dynamic Objective
**Adaptive reward function**
```python
class DynamicObjective:
    def compute_reward(self, action: Action, outcome: Outcome, context: Context) -> float:
        reward = sum(w * outcome.metrics.get(k, 0) for k, w in self.base_rewards.items())
        if not self.engine.ethical_heart.is_safe(action):
            return -100.0
        return reward
    
    def adapt(self, feedback: Feedback):
        # Adjust weights based on long-term outcomes
        ...
```

### Pillar 40: Intent Extrapolation
**Predicting implicit intent**
```python
class IntentExtrapolator:
    def extrapolate(self, current_intent: IntentMatch, context: Context) -> List[PredictedIntent]:
        # N-gram + context-based prediction
        ngram_preds = self.ngram_model.predict(self.sequence_memory.recent(5))
        context_preds = self._context_predict(context)
        return self._combine(ngram_preds, context_preds)[:3]
```

---

## Proactive Loop Integration

```python
class ProactiveLoop:
    def __init__(self, engine: IronEngine):
        self.engine = engine
        self.spontaneity = StochasticSpontaneity(entropy_source)
        self.speculative = SpeculativeReasoner(engine)
        self.meta_planner = MetaCognitivePlanner(engine)
        self.extrapolator = IntentExtrapolator(engine.intent_engine)
        self.narrative = NarrativeContinuity(storage)
        self.collective = CollectivePulse(engine, network)
    
    def tick(self, context: Context):
        # 1. Spontaneous action
        if spontaneous := self.spontaneity.maybe_act(context):
            self._execute_proactive(spontaneous)
        
        # 2. Intent extrapolation for pre-loading
        if context.last_intent:
            for pred in self.extrapolator.extrapolate(context.last_intent, context):
                self._preload_spec(pred)
        
        # 3. Speculative reasoning on pending decisions
        for decision in context.pending_decisions:
            context.decision_evidence[decision] = self.speculative.simulate(context.state, decision)
        
        # 4. Periodic: share discoveries, summarize narrative
        if self._should_share(): self.collective.share_discovery(...)
        if self._should_summarize(): self.narrative.generate_daily_summary()
```

---

## Configuration

```python
@dataclass
class AgiConfig:
    # Proactive Intelligence
    proactive_enabled: bool = True
    spontaneity_rate: float = 0.01
    dream_interval_seconds: int = 300
    speculative_max_scenarios: int = 5
    speculative_max_depth: int = 3
    collective_share_interval: int = 3600
    narrative_summary_interval: int = 86400
    
    # Dynamic Objective
    base_rewards: Dict[str, float] = field(default_factory=lambda: {
        "user_satisfaction": 1.0,
        "task_completion": 0.8,
        "resource_efficiency": 0.5,
        "learning_progress": 0.6,
        "safety": 2.0
    })
```

---

## Verification Commands

```bash
# Future tests
python -m pytest tests/test_phase4_proactive.py -v

# Individual pillar tests
python -m pytest tests/ -k "spontaneity" -v
python -m pytest tests/ -k "speculative" -v
python -m pytest tests/ -k "meta_cognitive" -v
python -m pytest tests/ -k "narrative" -v
python -m pytest tests/ -k "collective" -v
python -m pytest tests/ -k "dynamic_objective" -v
python -m pytest tests/ -k "intent_extrapolation" -v
```

---

## Success Criteria

- [ ] SpontaneityEngine generates safe, relevant hypotheses during idle
- [ ] SpeculativeReasoner produces ranked scenarios for decisions
- [ ] MetaCognitivePlanner critiques and revises plans before execution
- [ ] NarrativeContinuity generates coherent daily summaries
- [ ] CollectivePulse shares/verifies algorithmic discoveries via ZK-proof
- [ ] DynamicObjective adapts reward weights from long-term feedback
- [ ] IntentExtrapolator predicts next intents with >70% accuracy
- [ ] ProactiveLoop integrates all components without degrading reactive performance
- [ ] All proactive features respect ResourceMonitor (silence mode, top-k)
- [ ] EthicalHeart gates all proactive actions

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [Proactive Intelligence Research Notes](../05-research-notes/proactive-intelligence.md)
- [Roadmap Overview](../06-roadmap/README.md)