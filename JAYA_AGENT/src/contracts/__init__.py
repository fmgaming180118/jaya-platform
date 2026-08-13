"""
contracts package for JAYA_AGENT.

Exports typed contracts for Core → Agent → OS dispatch boundary.
"""

from .core_agent_os_contract import (
    AgentToolRequest,
    ContractValidationResult,
    ContractValidator,
    CoreToAgentDispatch,
    OsExecutionReceipt,
)

__all__ = [
    "AgentToolRequest",
    "ContractValidationResult",
    "ContractValidator",
    "CoreToAgentDispatch",
    "OsExecutionReceipt",
]
