import asyncio
from JAYA_CORE.src.sandbox import SandboxManager
from JAYA_CORE.src.sandbox.execution import ExecutionRequest, Language, ResourceLimits

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