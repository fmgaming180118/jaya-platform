import sys
import asyncio
import pytest

pytestmark = pytest.mark.manual
sys.path.insert(0, '.')

from jaya_core.os_kernel.ipc import (
    IPCRouter, BrainIPCClient, KernelIPCServer, InProcessIPCChannel,
    MessageType, IPCMessage, create_ipc_system
)

print('=== IPC System Debug Test with Handler Logging ===')

async def test_ipc():
    channel = InProcessIPCChannel()
    router = IPCRouter(channel)
    client = BrainIPCClient(router)
    server = KernelIPCServer(router)
    
    # Start router
    await router.start()
    
    # Add debug to router
    original_route = router._route_message
    async def debug_route(message):
        print(f'Router received: {message.type.value} from {message.source} to {message.target}')
        print(f'  correlation_id: {message.correlation_id}')
        print(f'  pending_requests: {list(router._pending_requests.keys())}')
        await original_route(message)
    router._route_message = debug_route
    
    # Add debug to handler
    original_handler = router._handlers.get(MessageType.PING)
    if original_handler:
        async def debug_handler(message):
            print(f'PING handler called for {message.message_id}')
            result = await original_handler(message) if asyncio.iscoroutinefunction(original_handler) else original_handler(message)
            print(f'PING handler returning: {result}')
            return result
        router._handlers[MessageType.PING] = debug_handler
    
    try:
        # Test ping - send directly to router's broadcast queue
        msg = IPCMessage.create(MessageType.PING, {}, source='brain_v2', target='os_kernel')
        print(f'Sending message: {msg.message_id} to {msg.target}')
        
        # Put message directly in broadcast queue for router
        await channel._broadcast_queue.put(msg)
        print('Message put in broadcast queue')
        
        # Give router time to process
        await asyncio.sleep(0.5)
        
        # Check if response is in brain_v2 queue
        try:
            response = await asyncio.wait_for(channel._queues['brain_v2'].get(), timeout=1.0)
            print(f'Response received: {response.payload}')
        except asyncio.TimeoutError:
            print('No response in brain_v2 queue')
        
        # Also check os_kernel queue
        try:
            kernel_msg = await asyncio.wait_for(channel._queues['os_kernel'].get(), timeout=0.1)
            print(f'Message in os_kernel queue: {kernel_msg.type.value}')
        except asyncio.TimeoutError:
            print('No message in os_kernel queue')
            
    finally:
        await router.stop()

asyncio.run(test_ipc())

print()
print('=== Debug Test COMPLETE ===')
