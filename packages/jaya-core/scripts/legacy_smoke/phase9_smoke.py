"""Phase 9 Integration Test"""
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

print('=== PHASE 9: INTEGRATION TEST ===')
print()

# --- Test 1: Ignite (loads model + vault) ---
print('--- Test 1: System Ignite ---')
from jaya_core.brain_v2.engine.runtime import IronEngine
engine = IronEngine(model_path, vault_password)
engine.ignite()
print(f'Awake: {engine.is_awake}')
print(f'Vault: {engine.vault}')
print()

# --- Test 2: Immune Audit (tensor check) ---
print('--- Test 2: Immune Audit ---')
from jaya_core.brain_v2.protection.immune import ImmuneSystem
immune = ImmuneSystem()

logits_safe = np.random.randn(100).astype(np.float32)
r1 = immune.audit_inference(logits_safe)
print(f'Safe logits:     {r1}')

logits_extreme = np.random.randn(100).astype(np.float32) * 200
r2 = immune.audit_inference(logits_extreme)
print(f'Extreme logits:  {r2}')

r3 = immune.audit_inference(logits_safe, decoded_text='rm -rf /')
print(f'Dangerous text:  {r3}')

r4 = immune.audit_inference(logits_safe, decoded_text='please delete the old files')
print(f'Review text:     {r4}')
print()

# --- Test 3: Socratic Mirror ---
print('--- Test 3: Socratic Mirror ---')
from jaya_core.brain_v2.soul.socratic import SocraticMirror
socratic = SocraticMirror()

dissent1 = socratic.review_inference(logits_safe, 'delete all backups', r4)
print(f'Delete intent:   {dissent1}')

dissent2 = socratic.review_inference(logits_safe, 'search for papers on AI', r1)
print(f'Safe intent:     {dissent2}')
print()

# --- Test 4: MemoryVault ---
print('--- Test 4: MemoryVault ---')
from jaya_core.brain_v2.protection.memory_vault import MemoryVault
from Crypto.Random import get_random_bytes
vault = MemoryVault(get_random_bytes(32))
vault.store('test_key', {'action': 'search', 'query': 'AI'})
recalled = vault.recall('test_key')
print(f'Stored + Recalled: {recalled}')

vault.store('temp', 'expire me', ttl=0.001)
time.sleep(0.01)
expired = vault.recall('temp')
print(f'Expired recall:    {expired}')

sealed = vault.seal()
print(f'Sealed: {sealed["total_entries"]} entries')
print()

print('=== ALL TESTS PASSED ===')
