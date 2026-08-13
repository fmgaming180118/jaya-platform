"""
verifier.py — Local testable verifier for Node and Jaya Identity.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .models import AuthorityLevel, JayaIdentity, NodeIdentity

logger = logging.getLogger(__name__)


class IdentityVerificationError(Exception):
    """Raised when identity verification fails."""


class LocalIdentityVerifier:
    """Verifies node registration and authority levels locally."""

    def __init__(self, master_identity: JayaIdentity) -> None:
        self.master_identity = master_identity
        self._registered_nodes: Dict[str, NodeIdentity] = {}

    def register_node(self, node: NodeIdentity) -> None:
        if node.jaya_identity_id != self.master_identity.identity_id:
            raise IdentityVerificationError(
                f"Node '{node.node_id}' claims jaya_identity '{node.jaya_identity_id}' "
                f"which does not match master identity '{self.master_identity.identity_id}'."
            )
        self._registered_nodes[node.node_id] = node
        logger.info("Registered node %s with authority %s", node.node_id, node.authority)

    def verify_node(self, node_id: str) -> NodeIdentity:
        if node_id not in self._registered_nodes:
            raise IdentityVerificationError(f"Node '{node_id}' is not registered.")
        return self._registered_nodes[node_id]

    def has_required_authority(self, node_id: str, min_authority: AuthorityLevel) -> bool:
        try:
            node = self.verify_node(node_id)
            return node.authority.value >= min_authority.value
        except IdentityVerificationError:
            return False
