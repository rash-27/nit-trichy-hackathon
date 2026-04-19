from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class BusState(BaseModel):
    isBusRunning: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    isAtStop: int = -1
    timeTillBusWaitsAtStop: Optional[int] = None # in seconds or unix timestamp based on usage
    upcoming_etas: List[Dict[str, Any]] = []
    current_segment_idx: int = -1
    segment_entry_time: float = 0.0

class StateManager:
    def __init__(self):
        self.state = BusState()

    def update_location(self, lat: float, lng: float, speed: float, isAtStop: int = -1, wait_time: Optional[int] = None):
        self.state.isBusRunning = True
        self.state.latitude = lat
        self.state.longitude = lng
        self.state.speed = speed
        self.state.isAtStop = isAtStop
        self.state.timeTillBusWaitsAtStop = wait_time

    def set_at_stop(self, is_at_stop: int, wait_time: Optional[int] = None):
        self.state.isAtStop = is_at_stop
        self.state.timeTillBusWaitsAtStop = wait_time

    def get_state_dict(self):
        return {
            "bus_state": self.state.model_dump()
        }

# Global singleton
app_state = StateManager()
