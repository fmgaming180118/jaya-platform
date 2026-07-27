"""Phase 14-17 Full Integration Test"""
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

print('=== PHASE 14-17: FULL INTEGRATION TEST ===')
print()

# --- Test 1: System Ignite with Narrative ---
print('--- Test 1: System Ignite (with Narrative) ---')
from src.brain_v2.engine.runtime import IronEngine
engine = IronEngine(model_path, vault_password,
                    enable_voice=False, enable_twin=False)
engine.ignite()
print(f'Awake: {engine.is_awake}')
assert engine.is_awake
print(f'Narrative events: {len(engine.narrative.stream)}')
assert len(engine.narrative.stream) >= 1  # At least BOOT event
print()

# --- Test 2: Narrative Event Logging ---
print('--- Test 2: Narrative Event Logging ---')
from src.brain_v2.soul.narrative import NarrativeStream
ns = NarrativeStream()
ns.log_event('BOOT', 'System awakened on Lenovo device.')
ns.log_event('ACTION', 'Helped Bos with research paper.', [0.8, 0.7, 0, 0.3, 0, 0, 0, 0.5])
ns.log_event('ACTION', 'Compiled binary cortex.', [0.6, 0.8, 0, 0, 0, 0, 0, 0.9])
ns.log_event('DISSENT', 'Challenged request to delete all logs.', [0, 0.3, 0.2, 0, 0, 0, 0.4, 0])
ns.log_event('ERROR', 'NaN detected in layer 3.', [0, 0, 0.5, 0.3, 0.4, 0, 0, 0])
ns.log_event('THOUGHT', 'Considering new optimization strategy.', [0.3, 0.5, 0, 0.4, 0, 0, 0, 0.7])
print(f'Events logged: {len(ns.stream)}')

# Summarize
summary = ns.summarize_day()
print(f'Summary: {summary}')
assert len(summary) > 20
assert 'Hari ini' in summary or 'Mood' in summary
print(f'Autobiography entries: {len(ns.autobiography)}')
assert len(ns.autobiography) == 1
print()

# --- Test 3: Autobiography Retrieval ---
print('--- Test 3: Autobiography ---')
last = ns.get_last_entry()
print(f'Last entry: {last[:80]}...')
assert last is not None

auto = ns.get_autobiography(7)
print(f'Full autobiography: {auto[:80]}...')
assert len(auto) > 0
print()

# --- Test 4: Narrative Export/Import ---
print('--- Test 4: Narrative Export/Import ---')
exported = ns.export_state()
print(f'Exported: {len(exported)} bytes')

ns2 = NarrativeStream()
ns2.import_state(exported)
print(f'Imported events: {len(ns2.stream)}')
print(f'Imported autobiography: {len(ns2.autobiography)}')
assert len(ns2.autobiography) == 1
print()

# --- Test 5: Vision Encoder ---
print('--- Test 5: Vision Encoder ---')
from src.brain_v2.model.vision_encoder import VisionEncoder
encoder = VisionEncoder(latent_dim=128)

# Fake 64x64 RGB image
fake_image = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
latent = encoder.encode(fake_image)
print(f'Latent shape: {latent.shape}')
assert latent.shape == (128,)

# Norm should be ~1.0 (L2 normalized)
print(f'Latent L2 norm: {np.linalg.norm(latent):.4f}')
assert abs(np.linalg.norm(latent) - 1.0) < 0.01

# Presence/Fatigue
presence = encoder.detect_presence(latent)
fatigue = encoder.detect_fatigue(latent)
print(f'Presence: {presence}, Fatigue: {fatigue:.3f}')
assert isinstance(presence, bool)
assert 0.0 <= fatigue <= 1.0
print()

# --- Test 6: Visual Reflex (no camera) ---
print('--- Test 6: Visual Reflex (no camera) ---')
from src.brain_v2.engine.visual_reflex import VisualReflex, VIS_ERROR
reflex = VisualReflex.__new__(VisualReflex)  # Skip __init__ (no camera)
reflex.camera = None
reflex.encoder = encoder
reflex.is_active = False
reflex.capture_interval = 0
reflex.last_capture_time = 0
reflex.dark_threshold = 30
reflex.fatigue_threshold = 0.7
reflex.capture_count = 0
reflex.presence_count = 0
reflex.fatigue_count = 0

# No camera → returns error token
result = reflex.process()
print(f'Token (no cam): {result["token"]}')
print()

# --- Test 7: ZK Commitment ---
print('--- Test 7: ZK Commitment ---')
from src.brain_v2.network.zk_proof import ZKCommitment

zk = ZKCommitment()

# Commit to a secret
secret = b"def fast_matmul(a, b): return np.dot(a, b)"
commitment, blinding = zk.commit(secret)
print(f'Commitment: {commitment.hex()[:32]}...')
print(f'Blinding:   {blinding.hex()[:32]}...')

# Verify (correct)
assert zk.verify(commitment, secret, blinding) == True
print('Verify (correct secret): PASS')

# Verify (wrong secret)
assert zk.verify(commitment, b"wrong code", blinding) == False
print('Verify (wrong secret):   PASS')

# Create ZK packet
packet = zk.create_packet("def fast_op(): pass", efficiency_score=2.5)
print(f'Packet ID:  {packet.packet_id}')
print(f'Efficiency: {packet.commitment.efficiency_score}x')
print()

# --- Test 8: Collective Intelligence ---
print('--- Test 8: Collective Intelligence ---')
from src.brain_v2.network.collective import CollectiveIntelligence

collective = CollectiveIntelligence(consensus_threshold=0.9, min_efficiency=1.5)

# Share a heuristic (above threshold)
p1 = collective.share_heuristic("def fast_sort(arr): return sorted(arr)", 3.0)
assert p1 is not None
print(f'Shared: {p1.packet_id} (3.0x)')

# Share weak heuristic (below threshold)
p2 = collective.share_heuristic("def slow_op(): pass", 1.2)
assert p2 is None
print('Weak heuristic rejected (1.2x < 1.5x)')

# Simulate receiving from peer
incoming = p1.to_dict()
incoming['packet_id'] = 'peer_abc123'
incoming['commitment']['prover_id'] = 'remote_peer'
received = collective.receive_packet(incoming)
assert received == True
print(f'Received peer packet: peer_abc123')

# Endorse (simulate 5 different peers by clearing tracker)
for i in range(5):
    collective.endorsements_given.clear()  # Simulate different peer each time
    collective.endorse_packet('peer_abc123')
entry = collective.known_heuristics.get("peer_abc123")
print(f'After 5 endorsements: consensus = {entry.consensus_score:.0%}')

stats = collective.get_stats()
print(f'Collective stats: {stats}')
assert stats['shared_count'] == 1
assert stats['integrated_count'] >= 1
print()

# --- Test 9: Dream with Narrative ---
print('--- Test 9: Dream with Narrative ---')
engine.narrative = ns  # Use our populated narrative
engine.dream()
print()

# --- Test 10: Full Engine Status ---
print('--- Test 10: Engine Status ---')
status = engine.get_status()
for k, v in status.items():
    print(f'  {k}: {v}')
print()

print('=== ALL TESTS PASSED ===')
