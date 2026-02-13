
import time
from typing import Dict, Any

from .awakening import AwakeningProtocol
from ..organism.metabolism import DigitalMetabolism
from ..protection.immune import ImmuneSystem

class IronEngine:
    """
    The Central Nervous System of JAYA.
    Manages the "Magnum Cycle":
    Sense -> Think -> Act -> Dream
    """
    def __init__(self, model_path: str, password: str):
        self.model_path = model_path
        self.password = password
        
        # Pillars
        self.loader = AwakeningProtocol(password)
        self.metabolism = DigitalMetabolism() # Pillar 2
        self.immune_system = ImmuneSystem()   # Pillar 14
        
        # State
        self.brain = None
        self.is_awake = False
        self.cycle_count = 0
        
    def ignite(self):
        """
        Boot Sequence.
        """
        print("\n=== SYSTEM IGNITION ===")
        self.brain = self.loader.awaken(self.model_path)
        if self.brain:
            self.is_awake = True
            print("=== SYSTEM ONLINE ===")
        else:
            print("=== SYSTEM FAILURE: IGNITION ABORTED ===")

    def run_magnum_cycle(self):
        """
        The Infinite Loop of Consciousness.
        """
        while self.is_awake:
            self.cycle_count += 1
            
            # 1. Sense (Input)
            input_signal = self.sense_environment()
            
            # 2. Metabolic Check (Pillar 7 - Cognitive Silence)
            energy_state = self.metabolism.check_vital_signs()
            if not input_signal and energy_state['mode'] == 'ECO':
                time.sleep(1)
                continue
                
            # 3. Think (Inference)
            print(f"[{self.cycle_count}] Thinking... (Energy: {energy_state['battery']}%)")
            logic_output = self.brain.forward([1, 2, 3])
            
            # 4. Act (Output)
            if self.immune_system.audit_action(logic_output):
                self.execute_action(logic_output)
            else:
                print("[!] Action Blocked by Immune System.")
                
            # 5. Dream (Maintenance)
            if self.cycle_count % 100 == 0:
                self.dream()
                
            # Dynamic Throttling (Pillar 2)
            sleep_duration = energy_state.get('suggested_sleep', 0.1)
            if self.cycle_count % 10 == 0 and sleep_duration > 0.5:
                print(f"[Metabolism] System Throttled: Sleeping {sleep_duration}s (Mode: {energy_state.get('mode')})")
            
            time.sleep(sleep_duration)

    def sense_environment(self) -> Any:
        return "Dummy Signal"

    def execute_action(self, output):
        pass

    def dream(self):
        print("... Dreaming (Consolidating Memory) ...")
