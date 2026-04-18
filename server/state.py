from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class BusState(BaseModel):
    isBusRunning: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    speed: Optional[float] = None
    isAtStop: bool = False
    timeTillBusWaitsAtStop: Optional[int] = None # in seconds or unix timestamp based on usage

class StateManager:
    def __init__(self):
        self.state = BusState()
        self.etas_to_stops = []

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
            "bus_state": self.state.model_dump(),
            "etas_to_stops": self.etas_to_stops
        }

# Global singleton
app_state = StateManager()
