import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from ws_manager import ws_manager
from state import app_state
from mqtt_client import start_mqtt_client

app = FastAPI(title="Transport Tracking Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Start MQTT loop in thread or background loop
    loop = asyncio.get_running_loop()
    start_mqtt_client(loop)
    print("Transport Tracking Server Started")

@app.get("/api/buses")
async def get_buses():
    return [{"name": "bus-1", "isRunning": app_state.state.isBusRunning}]

@app.websocket("/ws/bus_location")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Upon connection, send the initial current state
        initial_state = app_state.get_state_dict()
        await ws_manager.send_personal_message(initial_state, websocket)
        
        while True:
            # Client can send messages, but for now we just want to keep the connection open
            # and ignore client -> server messages
            data = await websocket.receive_text()
            pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
