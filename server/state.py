from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime

class BusState(BaseModel):
    isBusRunning: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    isAtStop: bool = False
    timeTillBusWaitsAtStop: Optional[int] = None # in seconds or unix timestamp based on usage
    upcoming_etas: List[Dict[str, Any]] = []

class StateManager:
    def __init__(self):
        self.state = BusState()

    def update_location(self, lat: float, lng: float, speed: float):
        self.state.isBusRunning = True
        self.state.latitude = lat
        self.state.longitude = lng
        self.state.speed = speed
        self.state.isAtStop = False
        self.state.timeTillBusWaitsAtStop = None

    def set_at_stop(self, is_at_stop: bool, wait_time: Optional[int] = None):
        self.state.isAtStop = is_at_stop
        self.state.timeTillBusWaitsAtStop = wait_time

    def get_state_dict(self):
        return {
            "bus_state": self.state.model_dump()
        }

# Global singleton
app_state = StateManager()
