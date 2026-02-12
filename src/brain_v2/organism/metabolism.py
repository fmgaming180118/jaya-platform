
import psutil
from typing import Dict, Any

try:
    # Requires psutil for sensors
    HAS_SENSORS = True
except ImportError:
    HAS_SENSORS = False
    
class DigitalMetabolism:
    """
    Pillar 2: Resource Aware.
    Pillar 7: Cognitive Silence.
    Pillar 10: Affective Metabolism.
    """
    def __init__(self):
        self.battery_threshold = 20 # %
        self.cpu_threshold = 80 # %

    def check_vital_signs(self) -> Dict[str, Any]:
        """
        Returns metabolic state with 'suggested_sleep' interval.
        Modes: PERFORMANCE, NORMAL, ECO, HIBERNATE.
        """
        status = {
            'battery': 100, 
            'cpu': 0, 
            'ram': 0,
            'mode': 'NORMAL',
            'suggested_sleep': 0.1 # Default 100ms
        }
        
        if not HAS_SENSORS:
             return status
             
        try:
            # 1. Battery Check
            battery = psutil.sensors_battery()
            if battery:
                status['battery'] = battery.percent
                if battery.percent < self.battery_threshold and not battery.power_plugged:
                    status['mode'] = 'ECO'
                    status['suggested_sleep'] = 1.0 # Slow down to 1s
            
            # 2. CPU Check
            status['cpu'] = psutil.cpu_percent(interval=None)
            if status['cpu'] > self.cpu_threshold:
                 status['mode'] = 'THROTTLED'
                 status['suggested_sleep'] = 0.5 # Cool down
                 
            # 3. RAM Check
            mem = psutil.virtual_memory()
            status['ram'] = mem.percent
            if mem.percent > 90:
                status['mode'] = 'CRITICAL_MEMORY'
                status['suggested_sleep'] = 2.0 # Heavy throttle to prevent crash
                
        except Exception as e:
            # Fallback if sensors fail
            print(f"[Metabolism] Error reading sensors: {e}")
            pass
            
        return status
