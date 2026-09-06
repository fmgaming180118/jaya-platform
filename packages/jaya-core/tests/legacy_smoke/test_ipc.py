import sys
import asyncio
import pytest

pytestmark = pytest.mark.manual
sys.path.insert(0, '.')

from jaya_core.os_kernel.ipc import (
    IPCRouter, BrainIPCClient, KernelIPCServer, InProcessIPCChannel,
    MessageType, IPCMessage, create_ipc_system
)

print('=== IPC System Test ===')

async def test_ipc():
    router, client, server = create_ipc_system()
    
    # Start router
    await router.start()
    
    try:
        # Test ping
        msg = IPCMessage.create(MessageType.PING, {}, source='brain_v2', target='os_kernel')
        response = await router.send_request(msg)
        print('Ping response: ' + str(response.payload))
        
        # Test feature list (will be empty since no registry)
        result = await client.list_features()
        print('Features: ' + str(result))
        
        # Test notification
        await client.notify('Test notification from brain_v2', 'info', 3000)
        print('Notification sent')
        
        # Test run_task
        result = await client.run_task('print("hello from task")', 'TEST_TASK')
        print('Run task: ' + str(result))
        
    finally:
        await router.stop()

asyncio.run(test_ipc())

print()
print('=== IPC System Test COMPLETE ===')
