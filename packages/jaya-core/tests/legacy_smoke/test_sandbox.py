import asyncio
import pytest

pytestmark = pytest.mark.manual
from jaya_core.sandbox import SandboxManager
from jaya_core.sandbox.execution import ExecutionRequest, Language, ResourceLimits

async def test():
    sandbox = SandboxManager()
    request = ExecutionRequest(
        code='print(1+1)',
        language=Language.PYTHON,
        resource_limits=ResourceLimits(max_wall_time_seconds=30),
        user_id='test_user',
    )
    result = await sandbox.execute(request)
    print('Status:', result.status)
    print('Stdout:', result.stdout)
    print('Stderr:', result.stderr)
    print('Exit code:', result.exit_code)

asyncio.run(test())
