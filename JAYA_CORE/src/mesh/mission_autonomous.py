"""
mission_autonomous.py — Mission Node Autonomous Mode & Decision Logger.

Runs Mission nodes in OFFLINE_AUTONOMOUS mode without network connectivity
for a simulated 10-minute operation window, logging all local decisions immutably.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.sync.contracts import NodeEvent
from src.sync.event_log import AppendOnlyEventLog

logger = logging.getLogger(__name__)


@dataclass
class DecisionLogRecord:
    decision_id: str
    action_title: str
    risk_class: str
    inputs: Dict[str, Any]
    timestamp: float
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutonomousMissionReport:
    mission_id: str
    node_id: str
    operation_mode: str  # "OFFLINE_AUTONOMOUS"
    total_duration_seconds: float
    decisions_count: int
    is_network_isolated: bool
    status: str  # "OFFLINE_AUTONOMOUS_SUCCESS"
    decisions: List[DecisionLogRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["decisions"] = [dec.to_dict() for dec in self.decisions]
        return d


class MissionNodeAutonomousRunner:
    """Runner managing Mission node execution in zero-connectivity OFFLINE_AUTONOMOUS mode."""

    def __init__(self, node_id: str, event_log: AppendOnlyEventLog) -> None:
        self.node_id = node_id
        self.event_log = event_log
        self.decisions: List[DecisionLogRecord] = []

    def record_autonomous_decision(
        self, action_title: str, risk_class: str = "REVERSIBLE", inputs: Optional[Dict[str, Any]] = None
    ) -> DecisionLogRecord:
        now = time.time()
        dec_id = f"dec-{self.node_id}-{len(self.decisions) + 1}"
        sig = f"sig-mission-{dec_id}"

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
            event_type="AUTONOMOUS_DECISION",
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
        """Run simulated mission operation window (default 600 seconds = 10 minutes)."""
        logger.info(
            "Starting Mission node %s in OFFLINE_AUTONOMOUS mode for %s seconds",
            self.node_id,
            simulated_duration_seconds,
        )

        # Record start, decision, and completion events
        self.record_autonomous_decision("INIT_AUTONOMOUS_NAVIGATION", risk_class="READ_ONLY")
        self.record_autonomous_decision("MAINTAIN_LOCAL_HOMEOSTASIS", risk_class="REVERSIBLE")
        self.record_autonomous_decision("CHECK_OBSTACLE_BOUNDARIES", risk_class="READ_ONLY")

        return AutonomousMissionReport(
            mission_id=mission_id,
            node_id=self.node_id,
            operation_mode="OFFLINE_AUTONOMOUS",
            total_duration_seconds=simulated_duration_seconds,
            decisions_count=len(self.decisions),
            is_network_isolated=True,
            status="OFFLINE_AUTONOMOUS_SUCCESS",
            decisions=list(self.decisions),
        )
