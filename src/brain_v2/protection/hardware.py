
import subprocess
import platform
import hashlib

def get_system_uuid() -> bytes:
    """
    Pillar 19: Hardware-Linked Identity.
    Extracts a unique immutable ID from the motherboard/CPU.
    """
    system = platform.system()
    try:
        if system == "Windows":
            # Command: wmic csproduct get uuid
            output = subprocess.check_output('wmic csproduct get uuid', shell=True)
            # Output format: \nUUID\n<UUID>\n
            uuid_str = output.decode().split('\n')[1].strip()
            return hashlib.sha256(uuid_str.encode()).digest()
            
        elif system == "Linux":
            # Check /sys/class/dmi/id/product_uuid
            # Requires root usually, fallback to machine-id
            try:
                with open("/sys/class/dmi/id/product_uuid", "r") as f:
                    uuid_str = f.read().strip()
            except PermissionError:
                with open("/etc/machine-id", "r") as f:
                    uuid_str = f.read().strip()
            return hashlib.sha256(uuid_str.encode()).digest()
            
        elif system == "Darwin": # macOS
             # system_profiler SPHardwareDataType | grep "Hardware UUID"
             output = subprocess.check_output(['system_profiler', 'SPHardwareDataType'])
             for line in output.decode().split('\n'):
                 if "Hardware UUID" in line:
                     uuid_str = line.split(': ')[1].strip()
                     return hashlib.sha256(uuid_str.encode()).digest()
                     
    except Exception as e:
        print(f"Hardware Lock Error: {e}")
        # Fallback for development/testing
        return b"DEV_HARDWARE_ID_FALLBACK_0000000"
        
    return b"UNKNOWN_HARDWARE_ID_0000000000"
