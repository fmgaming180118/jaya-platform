"""Phase 10-13 Full Integration Test"""
import os
import sys
import time

import numpy as np

sys.path.append(".")

model_path = os.environ.get("JAYA_CORE_MODEL_PATH")
vault_password = os.environ.get("JAYA_CORE_VAULT_PASSWORD")
if not model_path or not vault_password:
    raise SystemExit(
        "Set JAYA_CORE_MODEL_PATH and JAYA_CORE_VAULT_PASSWORD before running "
        "this legacy smoke script."
    )

print('=== PHASE 10-13: FULL INTEGRATION TEST ===')
print()

# --- Test 1: System Ignite with all pillars ---
print('--- Test 1: Full System Ignite ---')
from src.brain_v2.engine.runtime import IronEngine
engine = IronEngine(model_path, vault_password,
                    enable_voice=False, enable_twin=False)
engine.ignite()
print(f'Awake: {engine.is_awake}')
print(f'Vault: {engine.vault}')
print(f'Blueprint: {engine.dreamer.blueprint is not None}')
print(f'Blueprint layers: {len(engine.dreamer.blueprint) if engine.dreamer.blueprint else 0}')
print()

# --- Test 2: Epigenetic Path Selection ---
print('--- Test 2: Epigenetic Path Select ---')
from src.brain_v2.organism.epigenetics import EpigeneticProfile, InferencePath
epi = EpigeneticProfile()

# Simulate normal conditions
normal_vitals = {'cpu_temp': 50, 'battery': 80, 'battery_plugged': True, 'ram_percent': 40, 'cpu_percent': 30}
path = epi.evaluate(normal_vitals)
print(f'Normal vitals: {path.value}')
assert path == InferencePath.FULL

# Simulate overheating
epi.cooldown_seconds = 0  # disable cooldown for test
hot_vitals = {'cpu_temp': 95, 'battery': 80, 'battery_plugged': True, 'ram_percent': 40, 'cpu_percent': 30}
path = epi.evaluate(hot_vitals)
print(f'Overheating:   {path.value}')
assert path == InferencePath.REFLEX

# Recovery
cool_vitals = {'cpu_temp': 60, 'battery': 80, 'battery_plugged': True, 'ram_percent': 40, 'cpu_percent': 30}
path = epi.evaluate(cool_vitals)
print(f'Cooled down:   {path.value}')
assert path == InferencePath.FULL
print()

# --- Test 3: Reflex Path (skip attention) ---
print('--- Test 3: Reflex Path Inference ---')
tokens = [1, 2, 3]
full_out = engine.brain.forward(tokens, skip_attention=False)
reflex_out = engine.brain.forward(tokens, skip_attention=True)
print(f'Full output:   shape={full_out.shape}, mean={np.mean(full_out):.4f}')
print(f'Reflex output: shape={reflex_out.shape}, mean={np.mean(reflex_out):.4f}')
print(f'Different:     {not np.allclose(full_out, reflex_out)}')
print()

# --- Test 4: Metabolism Telemetry ---
print('--- Test 4: Real Telemetry ---')
from src.brain_v2.organism.metabolism import DigitalMetabolism
meta = DigitalMetabolism()
vitals = meta.check_vital_signs()
print(f'Battery: {vitals["battery"]}%')
print(f'CPU:     {vitals["cpu_percent"]}%')
print(f'RAM:     {vitals["ram_percent"]}%')
print(f'Temp:    {vitals["cpu_temp"]}C')
print(f'Mode:    {vitals["mode"]}')
print()

# --- Test 5: Neural Regeneration ---
print('--- Test 5: Neural Regeneration ---')
from src.brain_v2.organism.regeneration import NeuralRegenerator
regen = NeuralRegenerator()
bp = regen.create_blueprint(engine.brain)

# Scan (should be clean)
corrupted = regen.scan_integrity(engine.brain, bp)
assert len(corrupted) == 0

# Corrupt a weight deliberately (flip many bytes to change CRC32)
w = engine.brain.output_head.weights
w_view = w.view(np.uint8)
w_view[:100] = 255 - w_view[:100]  # Flip bits in first 100 bytes
corrupted = regen.scan_integrity(engine.brain, bp)
print(f'After corruption: {len(corrupted)} damaged layers')
assert len(corrupted) > 0

# Regenerate
fixed = regen.regenerate(engine.brain, bp, corrupted)
print(f'Regenerated: {fixed} layers')
assert fixed > 0
print()

# --- Test 6: Dream + Full Maintenance ---
print('--- Test 6: Dream Cycle ---')
engine.dreamer.create_blueprint(engine.brain)  # refresh blueprint
engine.dream()
print()

# --- Test 7: Twin Sync ---
print('--- Test 7: Twin Sync ---')
from src.brain_v2.network.twin_sync import TwinSync
from src.brain_v2.protection.memory_vault import MemoryVault
from Crypto.Random import get_random_bytes

sync = TwinSync()
key = get_random_bytes(32)
vault_a = MemoryVault(key)
vault_b = MemoryVault(key)

vault_a.store('shared_1', 'hello from A')
vault_a.store('shared_2', 'data from A')
vault_b.store('shared_3', 'hello from B')

# Sync A → B
sealed_a = vault_a.seal()
result = sync.merge_vaults(vault_b, sealed_a, peer_id='device_A')
print(f'Merge A→B: {result}')
assert result.merged_count == 2
print(f'B now has: {vault_b.count} entries')
print()

# --- Test 8: Get Status ---
print('--- Test 8: Engine Status ---')
status = engine.get_status()
for k, v in status.items():
    print(f'  {k}: {v}')
print()

print('=== ALL TESTS PASSED ===')
