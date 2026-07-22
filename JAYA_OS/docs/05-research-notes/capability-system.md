# Capability System — JAYA_OS

## Overview

The capability system is the foundation of JAYA_OS security. It implements **capability-based security** where features must explicitly declare and be granted capabilities to access system resources.

---

## Capability Model

### What is a Capability?

A **capability** is an unforgeable token of authority that grants access to a specific resource or operation. In JAYA_OS:

- Capabilities are **fine-grained** (not coarse roles)
- Capabilities are **declarative** (declared in feature manifest)
- Capabilities are **enforced** at runtime by proxies
- Capabilities are **auditable** (all usage logged)

### Capability vs Permission

| Aspect | Permission (Traditional) | Capability (JAYA_OS) |
|---|---|---|
| Granularity | Coarse (read/write/execute) | Fine (specific paths, domains) |
| Delegation | Difficult | Natural (pass capability) |
| Revocation | Complex | Simple (revoke proxy) |
| Audit | Coarse | Fine-grained |

---

## Capability Types

### 1. Filesystem Capabilities

| Capability | Description | Config |
|---|---|---|
| `fs_read` | Read files | `allowed_paths: ["./data", "./features"]` |
| `fs_write` | Write files | `allowed_paths: ["./features/tmp"]` |
| `fs_list` | List directories | `allowed_paths: ["./features"]` |
| `fs_exec` | Execute files | `allowed_paths: ["./features/bin"]` |

### 2. Network Capabilities

| Capability | Description | Config |
|---|---|---|
| `net_http` | HTTP/HTTPS requests | `allowed_domains: ["api.github.com"]` |
| `net_tcp` | Raw TCP connections | `allowed_ports: [80, 443]` |
| `net_udp` | UDP datagrams | `allowed_ports: [53]` |
| `net_listen` | Listen on ports | `allowed_ports: [8080-8090]` |

### 3. Hardware Capabilities

| Capability | Description | Config |
|---|---|---|
| `hw_display` | Display output | `monitors: ["primary"]` |
| `hw_input` | Keyboard/mouse | `devices: ["keyboard", "mouse"]` |
| `hw_audio` | Audio I/O | `devices: ["default"]` |
| `hw_camera` | Camera access | `devices: ["front"]` |
| `hw_gpio` | GPIO pins | `pins: [17, 18, 27]` |
| `hw_usb` | USB devices | `vendors: ["0x1234"]` |

### 4. System Capabilities

| Capability | Description | Config |
|---|---|---|
| `sys_process` | Spawn processes | `allowed_commands: ["python", "node"]` |
| `sys_info` | System information | `fields: ["cpu", "memory", "disk"]` |
| `sys_config` | Modify config | `keys: ["theme", "language"]` |
| `sys_time` | Time operations | `allow_set: false` |

### 5. IPC Capabilities

| Capability | Description | Config |
|---|---|---|
| `ipc_send` | Send messages | `channels: ["features", "system"]` |
| `ipc_receive` | Receive messages | `channels: ["features"]` |
| `ipc_broadcast` | Broadcast messages | `channels: ["system"]` |

### 6. Memory Capabilities

| Capability | Description | Config |
|---|---|---|
| `mem_read` | Read shared memory | `regions: ["feature_state"]` |
| `mem_write` | Write shared memory | `regions: ["feature_state"]` |
| `mem_alloc` | Allocate memory | `max_mb: 100` |

---

## Capability Declaration

### In Feature Manifest

```json
{
  "name": "data_processor",
  "version": "1.0.0",
  "entry_point": "main:run",
  "capabilities": [
    {
      "name": "fs_read",
      "config": {
        "allowed_paths": ["./data", "./features"]
      }
    },
    {
      "name": "fs_write",
      "config": {
        "allowed_paths": ["./features/tmp"]
      }
    },
    {
      "name": "net_http",
      "config": {
        "allowed_domains": ["api.github.com", "api.nvidia.com"],
        "max_requests_per_minute": 10
      }
    },
    {
      "name": "ipc_send",
      "config": {
        "channels": ["features"]
      }
    }
  ]
}
```

---

## Capability Resolution

### At Mount Time

```
1. Feature manifest parsed
2. Capabilities extracted
3. Each capability validated:
   - Is capability known?
   - Is config valid for capability type?
   - Does feature have required signatures?
4. Capability proxies created
5. Proxies injected into feature namespace
```

### At Runtime

```
Feature calls proxy method
        │
        ▼
Proxy validates request against config
        │
        ├─► Allowed → Forward to system
        │
        └─► Denied → Raise PermissionError, log audit
```

---

## Capability Delegation

Features can **delegate** capabilities to sub-features or child processes:

```python
# Parent feature delegates subset of its capabilities
child_config = {
    "name": "child_feature",
    "capabilities": [
        {
            "name": "fs_read",
            "config": {
                "allowed_paths": ["./features/tmp/child_data"]  # Subset of parent's paths
            }
        }
    ]
}
```

**Rules:**
- Can only delegate capabilities you possess
- Delegated capabilities must be **subset** of your own
- Delegation is **revocable** by parent

---

## Capability Revocation

### Automatic Revocation
- Feature unmount → all capabilities revoked
- Feature error → capabilities suspended
- Resource limit exceeded → capabilities throttled

### Manual Revocation
```python
# JayaBridge revokes capability
bridge.revoke_capability(feature_id, "net_http")

# Or revoke all
bridge.revoke_all_capabilities(feature_id)
```

---

## Capability Inheritance

### Feature Dependencies
When feature A depends on feature B:
- A inherits B's **public** capabilities (if declared)
- A can **extend** B's capabilities with its own
- Circular dependencies prohibited

```json
{
  "name": "feature_a",
  "dependencies": ["feature_b"],
  "capabilities": [
    {
      "name": "fs_write",
      "config": {
        "allowed_paths": ["./features/tmp/a"]  # Extends B's paths
      }
    }
  ]
}
```

---

## Capability Auditing

### Audit Log Format
```json
{
  "timestamp": "2026-07-21T10:30:00.123Z",
  "feature_id": "data_processor_123",
  "capability": "fs_read",
  "resource": "./data/users.csv",
  "action": "read",
  "result": "allowed",
  "duration_ms": 2.3,
  "stack_trace": "optional"
}
```

### Audit Queries
```python
# All capability uses by feature
audit.query(feature_id="data_processor_123")

# All denied attempts
audit.query(result="denied")

# Capability usage over time
audit.query(capability="net_http", since="2026-07-20")
```

---

## Capability Policy Engine

### Policy Definition
```python
@dataclass
class CapabilityPolicy:
    # Default policies for new features
    default_capabilities: List[str] = field(default_factory=list)
    
    # Maximum capabilities per feature
    max_capabilities_per_feature: int = 10
    
    # Capability-specific policies
    capability_policies: Dict[str, CapabilityPolicyRule] = field(default_factory=dict)
    
    # Global limits
    global_limits: Dict[str, Any] = field(default_factory=lambda: {
        "max_fs_read_paths": 10,
        "max_fs_write_paths": 5,
        "max_net_domains": 20,
        "max_ipc_channels": 5,
    })

@dataclass
class CapabilityPolicyRule:
    require_signature: bool = False
    require_approval: bool = False
    max_instances: int = 1
    allowed_config_keys: List[str] = field(default_factory=list)
    forbidden_config_values: List[str] = field(default_factory=list)
```

### Example Policy
```python
policy = CapabilityPolicy(
    default_capabilities=["fs_read"],
    max_capabilities_per_feature=8,
    capability_policies={
        "net_http": CapabilityPolicyRule(
            require_signature=True,
            require_approval=True,
            max_instances=1,
            allowed_config_keys=["allowed_domains", "max_requests_per_minute"],
            forbidden_config_values=["*", "localhost", "127.0.0.1"]
        ),
        "sys_process": CapabilityPolicyRule(
            require_signature=True,
            require_approval=True,
            max_instances=0,  # Not allowed by default
        ),
    }
)
```

---

## Capability Verification

### Static Verification (Mount Time)
```python
def verify_capabilities(manifest: FeatureManifest, policy: CapabilityPolicy) -> VerificationResult:
    errors = []
    
    # Check count
    if len(manifest.capabilities) > policy.max_capabilities_per_feature:
        errors.append(f"Too many capabilities: {len(manifest.capabilities)} > {policy.max_capabilities_per_feature}")
    
    # Check each capability
    for cap in manifest.capabilities:
        rule = policy.capability_policies.get(cap.name)
        if rule:
            if rule.require_signature and not manifest.signature:
                errors.append(f"Capability {cap.name} requires signed manifest")
            if rule.require_approval and not manifest.approved:
                errors.append(f"Capability {cap.name} requires approval")
            
            # Check config keys
            for key in cap.config:
                if key not in rule.allowed_config_keys:
                    errors.append(f"Capability {cap.name}: unknown config key {key}")
            
            # Check forbidden values
            for key, value in cap.config.items():
                if value in rule.forbidden_config_values:
                    errors.append(f"Capability {cap.name}: forbidden value {value} for {key}")
    
    return VerificationResult(valid=len(errors)==0, errors=errors)
```

### Dynamic Verification (Runtime)
```python
class CapabilityVerifier:
    def __init__(self, policy: CapabilityPolicy):
        self.policy = policy
    
    def verify_request(self, feature_id: str, capability: str, 
                       resource: str, action: str) -> bool:
        # Check feature has capability
        feature_caps = self.get_feature_capabilities(feature_id)
        cap = feature_caps.get(capability)
        if not cap:
            return False
        
        # Check resource against config
        if not self._resource_allowed(cap.config, resource, action):
            return False
        
        # Check global limits
        if not self._check_global_limits(capability, action):
            return False
        
        return True
```

---

## Testing Capabilities

```bash
# Test capability declaration
python -m pytest tests/ -k "capability_declaration" -v

# Test capability enforcement
python -m pytest tests/ -k "capability_enforcement" -v

# Test capability delegation
python -m pytest tests/ -k "capability_delegation" -v

# Test capability revocation
python -m pytest tests/ -k "capability_revocation" -v

# Test policy engine
python -m pytest tests/ -k "capability_policy" -v

# Full capability system
python -m pytest tests/ -k "capability" -v
```

---

## Future Enhancements

| Feature | Description |
|---|---|
| **Capability Marketplace** | Features can request capabilities from other features |
| **Time-limited Capabilities** | Capabilities that expire after TTL |
| **Conditional Capabilities** | Capabilities granted based on context (time, location, user) |
| **Capability Composition** | Combine multiple capabilities into higher-level ones |
| **Capability Negotiation** | Features negotiate capabilities at mount time |

---

## 🔗 Related Docs

- [Sandbox Isolation](../05-research-notes/sandbox-isolation.md) — Capability proxies
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Runtime Features](../03-features/runtime-features.md) — Feature manifests
- [Architecture Overview](../02-architecture/overview.md)