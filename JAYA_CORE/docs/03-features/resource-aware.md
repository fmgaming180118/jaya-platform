# Resource-Aware Cognition — JAYA_CORE

## Overview

JAYA_CORE integrates **hardware resource awareness** directly into cognitive loops. The brain adapts its computation intensity based on real-time CPU, RAM, and battery conditions.

---

## ResourceMonitor (Pillar 2)

### `src/brain_v2/organism/resource_monitor.py`

```python
class ResourceMonitor:
    def __init__(self, 
                 check_interval: float = 5.0,
                 high_cpu_threshold: float = 85.0,
                 low_cpu_threshold: float = 40.0):
        self.check_interval = check_interval
        self.high_cpu_threshold = high_cpu_threshold
        self.low_cpu_threshold = low_cpu_threshold
        self._engine: Optional[IronEngine] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._silence_active = False
        self._last_readings = {}
    
    def attach(self, engine: IronEngine) -> None:
        """Attach to engine and start monitoring."""
        self._engine = engine
        self.start()
    
    def start(self) -> None:
        """Start background monitoring thread."""
        ...
    
    def stop(self) -> None:
        """Stop monitoring thread."""
        ...
    
    def _tick(self) -> None:
        """Single monitoring cycle."""
        readings = get_readings()  # {cpu_pct, mem_pct, battery_pct}
        self._last_readings = readings
        
        if self._engine is None:
            return
        
        cpu = readings["cpu_pct"]
        
        # Silence mode triggers
        if cpu >= self.high_cpu_threshold and not self._silence_active:
            self._engine.enter_silence()
            self._silence_active = True
        elif cpu <= self.low_cpu_threshold and self._silence_active:
            self._engine.exit_silence()
            self._silence_active = False
        
        # Dynamic top-k adjustment
        self._adjust_topk_ratio(cpu)
        
        # User callbacks
        for condition_fn, action_fn in self._callbacks:
            if condition_fn(readings):
                action_fn(readings, self._engine)
    
    def _adjust_topk_ratio(self, cpu: float) -> None:
        """Adjust cognitive intensity based on CPU."""
        if cpu < 30.0:
            target = 0.10   # Full capacity
        elif cpu < 60.0:
            target = 0.07
        elif cpu < 80.0:
            target = 0.04
        else:
            target = 0.02   # Minimal firing
        
        if abs(self._engine.config.topk_ratio - target) > 0.01:
            self._engine.config.topk_ratio = target
```

---

## Cognitive Adaptation Strategies

### 1. Activation Sparsity (Pillar 35) — Top-K Adaptive

**Mechanism:** Only activate top-k neurons/paths based on resource availability.

| CPU% | topk_ratio | Cognitive Effect |
|---|---|---|
| < 30% | 0.10 | Full reasoning, all paths active |
| 30-60% | 0.07 | Moderate pruning |
| 60-80% | 0.04 | Significant pruning |
| ≥ 80% | 0.02 | Minimal firing (survival mode) |

**Implementation in IronEngine:**
```python
def execute_intent(self, intent: IntentMatch) -> ExecutionResult:
    # Apply top-k sparsity to reasoning paths
    active_paths = self._select_top_k_paths(
        all_paths, 
        k=int(len(all_paths) * self.config.topk_ratio)
    )
    return self._execute_paths(active_paths)
```

### 2. Cognitive Silence (Pillar 7)

**Trigger:** CPU ≥ 85% (configurable)

**Behavior:**
- Suspend non-critical background processes
- Reduce `topk_ratio` to minimum (0.02)
- Defer learning/consolidation
- Maintain only: safety monitors, critical intent handling

**Exit:** CPU ≤ 40% → restore normal operation

### 3. Dynamic MoE Routing (Pillar 34)

**Mechanism:** Route to fewer experts under resource pressure.

```python
def route_to_experts(self, input: Tensor, cpu_pct: float) -> Tensor:
    if cpu_pct > 80:
        num_experts = 1  # Single expert
    elif cpu_pct > 60:
        num_experts = 2
    else:
        num_experts = 4  # Full ensemble
    
    return self.moe_layer(input, num_experts=num_experts)
```

### 4. Cache Management

**Strategy:** Bound cache size, evict based on resource pressure.

```python
class PlanCache:
    def __init__(self, max_size: int = 1000, max_memory_mb: int = 100):
        self.max_size = max_size
        self.max_memory = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict[str, CachedPlan] = OrderedDict()
    
    def get(self, key: str) -> Optional[CachedPlan]:
        if key in self.cache:
            self.cache.move_to_end(key)  # LRU
            return self.cache[key]
        return None
    
    def put(self, key: str, plan: CachedPlan) -> None:
        # Evict if over memory budget
        while self._current_memory() > self.max_memory:
            self.cache.popitem(last=False)  # Remove oldest
        self.cache[key] = plan
```

---

## Battery-Aware Operation (Mobile/Laptop)

### Battery Readings
```python
def get_readings() -> Dict[str, float]:
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    bat = -1.0
    battery = psutil.sensors_battery()
    if battery is not None:
        bat = battery.percent
    return {"cpu_pct": cpu, "mem_pct": mem, "battery_pct": bat}
```

### Battery Policies

| Battery% | Policy |
|---|---|
| > 50% | Normal operation |
| 20-50% | Reduce background tasks, lower topk_ratio by 1 level |
| 10-20% | Cognitive silence mode, defer all non-critical |
| < 10% | Emergency mode: only safety-critical functions |

---

## Integration with Cognitive Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RESOURCE-AWARE COGNITIVE LOOP                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ResourceMonitor (5s interval)                                              │
│       │                                                                     │
│       ├─► readings = {cpu_pct, mem_pct, battery_pct}                       │
│       │                                                                     │
│       ├─► CPU ≥ 85% → IronEngine.enter_silence()                           │
│       │                                                                     │
│       ├─► CPU ≤ 40% → IronEngine.exit_silence()                            │
│       │                                                                     │
│       └─► Dynamic topk_ratio:                                               │
│           CPU < 30%  → 0.10 (full)                                          │
│           CPU < 60%  → 0.07                                                 │
│           CPU < 80%  → 0.04                                                 │
│           CPU ≥ 80%  → 0.02 (minimal)                                       │
│                                                                             │
│  IronEngine.execute_intent()                                                │
│       │                                                                     │
│       ├─► Apply topk_ratio to path selection                               │
│       │                                                                     │
│       ├─► If silence_mode: minimal reasoning only                          │
│       │                                                                     │
│       └─► EthicalHeart gate (always active)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### AgiConfig (Resource Section)
```python
@dataclass
class AgiConfig:
    # Resource Monitor
    resource_check_interval: float = 5.0
    high_cpu_threshold: float = 85.0
    low_cpu_threshold: float = 40.0
    
    # Sparsity
    topk_ratio: float = 0.10
    min_topk_ratio: float = 0.02
    max_topk_ratio: float = 0.10
    
    # Battery
    battery_critical_threshold: float = 10.0
    battery_low_threshold: float = 20.0
    battery_medium_threshold: float = 50.0
    
    # Cache
    plan_cache_size: int = 1000
    plan_cache_memory_mb: int = 100
```

### Environment Variables
```bash
JAYA_RESOURCE_CHECK_INTERVAL=5.0
JAYA_HIGH_CPU_THRESHOLD=85.0
JAYA_LOW_CPU_THRESHOLD=40.0
```

---

## Testing Resource Awareness

```bash
# Resource Monitor Tests
python -m pytest tests/test_new_pillars.py::test_resource_monitor_readings -v
python -m pytest tests/test_new_pillars.py::test_resource_monitor_start_stop -v

# Activation Sparsity Gate
python -m pytest tests/test_phase1_activation_sparsity_gate.py -v

# Dynamic MoE Gate
python -m pytest tests/test_phase1_dynamic_moe_gate.py -v

# Full integration under load
python -m pytest tests/test_phase1_ir_benchmark.py -v
```

### Simulating Load
```python
# In test: simulate high CPU
import psutil
# Or mock ResourceMonitor.get_readings()
with patch('src.brain_v2.organism.resource_monitor.get_readings') as mock:
    mock.return_value = {"cpu_pct": 90.0, "mem_pct": 50.0, "battery_pct": 80.0}
    engine.execute_intent(intent)
    assert engine.config.silence_mode == True
```

---

## Metrics & Observability

### Key Metrics
| Metric | Target | Alert Threshold |
|---|---|---|
| `cpu_pct` | < 60% avg | > 85% sustained |
| `mem_pct` | < 70% | > 90% |
| `topk_ratio` | 0.10 (idle) | < 0.02 (silence) |
| `silence_mode_duration` | < 30s | > 60s |
| `cache_hit_rate` | > 95% | < 80% |
| `plan_cache_size` | < 1000 | > 2000 |

### Status Endpoint
```python
engine.status()
# Returns:
{
    "silence_mode": False,
    "topk_ratio": 0.10,
    "resource_readings": {"cpu_pct": 25.3, "mem_pct": 45.1, "battery_pct": 87.0},
    "cache_stats": {"size": 847, "hit_rate": 0.97, "memory_mb": 42.3},
    "ethical_state": "ACTIVE",
    "uptime_seconds": 3600
}
```

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — ResourceMonitor in pipeline
- [API Reference](../02-architecture/api-reference.md) — ResourceMonitor, IronEngine interfaces
- [Cognitive Features](cognitive-features.md) — Base cognitive pipeline
- [Roadmap Phase 1](../06-roadmap/phase-1-cognitive-foundation.md) — Resource-aware execution