"""
test_portable_kernel.py — Unit test for Portable Cognitive Kernel in JAYA_CORE.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

from JAYA_CORE.src.cognitive.contracts import UserRequest
from JAYA_CORE.src.cognitive.portable_kernel import PORTABLE_MAX_RAM_MB, PortableCognitiveKernelRunner


class TestPortableCognitiveKernelRunner:
    def test_portable_cognitive_kernel_execution(self):
        runner = PortableCognitiveKernelRunner()
        req = UserRequest(request_id="req-test-1", raw_prompt="Hello kernel")

        res = runner.run_portable_request(req)
        assert res.status == "PORTABLE_KERNEL_READY"
        assert res.metrics.total_memory_mb <= PORTABLE_MAX_RAM_MB
        assert len(res.components_status) == 11


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
