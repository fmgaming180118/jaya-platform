"""
mission_autonomous.py — Mission Node Autonomous Mode & Decision Logger.

STATUS: PROTOTYPE / SIMULATION ONLY

This module is a PROTOTYPE/SCAFFOLD only. It does NOT:
- Actually run for 10 minutes (just returns immediately with hardcoded duration)
- Process real sensor data
- Perform real reasoning or decision-making
- React to environment changes
- Handle failures or network disconnection
- Measure real latency or resource usage

Current implementation:
- Records 3 hardcoded decisions immediately
- Returns a report with simulated_duration_seconds (default 600s)
- Does NOT actually wait or run autonomously

MUST NOT be claimed as "10-minute offline autonomous operation" or real autonomy.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from jaya_core.sync.contracts import NodeEvent
from jaya_core.sync.event_log import AppendOnlyEventLog

logger = logging.getLogger(__name__)


@dataclass
class DecisionLogRecord:
    decision_id: str
    action_title: str
    risk_class: str
    inputs: Dict[str, Any]
    timestamp: float
    signature: str  # PROTOTYPE: not cryptographic

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomousMissionReport:
    mission_id: str
    node_id: str
    operation_mode: str  # "OFFLINE_AUTONOMOUS_PROTOTYPE"
    total_duration_seconds: float  # SIMULATED - not actual runtime
    decisions_count: int
    is_network_isolated: bool
    status: str  # "PROTOTYPE_SIMULATION"
    decisions: List[DecisionLogRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decisions"] = [dec.to_dict() for dec in self.decisions]
        return d


class MissionNodeAutonomousRunner:
    """
    Mission node autonomous runner - CURRENTLY A PROTOTYPE/SIMULATION.
    
    Does NOT:
    - Run for actual duration (returns immediately)
    - Process sensors or environment
    - Perform real reasoning
    - Handle failures
    - Measure real performance
    
    Only provides:
    - Hardcoded decision logging demonstration
    - Contract structure for future real implementation
    """

    def __init__(self, node_id: str, event_log: AppendOnlyEventLog) -> None:
        self.node_id = node_id
        self.event_log = event_log
        self.decisions: List[DecisionLogRecord] = []
        logger.warning("MissionNodeAutonomousRunner initialized - THIS IS A PROTOTYPE: no real autonomy, no 10-min runtime")

    def record_autonomous_decision(
        self, action_title: str, risk_class: str = "REVERSIBLE", inputs: Optional[Dict[str, Any]] = None
    ) -> DecisionLogRecord:
        now = time.time()
        dec_id = f"dec-{self.node_id}-{len(self.decisions) + 1}"
        sig = f"sig-mission-{dec_id}"  # PROTOTYPE: not cryptographic

        record = DecisionLogRecord(
            decision_id=dec_id,
            action_title=action_title,
            risk_class=risk_class,
            inputs=inputs or {},
            timestamp=now,
            signature=sig,
        )
        self.decisions.append(record)

        # Log decision in local append-only event log
        event = NodeEvent(
            event_id=f"evt-{dec_id}",
            event_type="AUTONOMOUS_DECISION_PROTOTYPE",
            node_id=self.node_id,
            sequence_number=len(self.decisions),
            payload=record.to_dict(),
            timestamp=str(now),
            signature=sig,
        )
        self.event_log.append_raw(event)
        return record

    def run_mission_window(
        self, mission_id: str, simulated_duration_seconds: float = 600.0
    ) -> AutonomousMissionReport:
        """
        PROTOTYPE: Returns immediately with hardcoded decisions.
        Does NOT actually run for simulated_duration_seconds.
        """
        logger.warning(
            "MissionNodeAutonomousRunner.run_mission_window() called - PROTOTYPE: "
            "returns immediately with %d hardcoded decisions, does NOT run for %.1f seconds",
            3, simulated_duration_seconds
        )

        # Record 3 hardcoded decisions immediately (no actual autonomy)
        self.record_autonomous_decision("INIT_AUTONOMOUS_NAVIGATION_PROTOTYPE", risk_class="READ_ONLY")
        self.record_autonomous_decision("MAINTAIN_LOCAL_HOMEOSTASIS_PROTOTYPE", risk_class="REVERSIBLE")
        self.record_autonomous_decision("CHECK_OBSTACLE_BOUNDARIES_PROTOTYPE", risk_class="READ_ONLY")

        return AutonomousMissionReport(
            mission_id=mission_id,
            node_id=self.node_id,
            operation_mode="OFFLINE_AUTONOMOUS_PROTOTYPE",
            total_duration_seconds=simulated_duration_seconds,  # SIMULATED
            decisions_count=len(self.decisions),
            is_network_isolated=True,
            status="PROTOTYPE_SIMULATION",
            decisions=list(self.decisions),
        )
