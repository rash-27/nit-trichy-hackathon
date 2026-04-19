import json
import logging
import asyncio
import paho.mqtt.client as mqtt

from state import app_state
from route_manager import route_manager
from ml_model import ml_estimator
from ws_manager import ws_manager
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MQTT_Client")

# HiveMQ Configuration
BROKER = os.getenv("MQTT_BROKER")
PORT = int(os.getenv("MQTT_PORT", "8883"))
TOPIC = os.getenv("MQTT_TOPIC")
USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

def process_payload(payload):
    """
    Update the state and calculate ETAs based on the payload.
    Returns the update message to broadcast.
    """
    try:
        lat = payload.get("lat")
        lng = payload.get("lng")
        speed = payload.get("speed_kmh", 0)
        isAtStop = payload.get("isAtStop", -1)
        wait_time = payload.get("timeTillBusWaitsAtStop")

        # Update global memory state
        app_state.update_location(lat, lng, speed, isAtStop, wait_time)

        # ETA Calculation
        seg_idx, dist_covered = route_manager.get_current_segment_and_progress(lat, lng)

        # DB Analytics
        import time
        import datetime
        import asyncio
        from db import insert_segment_time
        from ml_model import DAY_PROFILES, HOUR_MULTIPLIERS

        current_segment = app_state.state.current_segment_idx
        entry_time = app_state.state.segment_entry_time
        bus_id = payload.get("bus_id", "bus_1")
        timestamp = payload.get("timestamp", time.time())

        if current_segment != -1 and seg_idx != current_segment:
            if entry_time > 0:
                elapsed_s = timestamp - entry_time
                segment_dist_m = route_manager.segments[current_segment]["total_distance_km"] * 1000
                d = datetime.datetime.fromtimestamp(timestamp)
                day_int = d.weekday()
                hour_int = d.hour
                profile = DAY_PROFILES.get(day_int, DAY_PROFILES[0])
                hma = HOUR_MULTIPLIERS.get(hour_int, 1.0)
                
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(insert_segment_time(
                        timestamp, bus_id, current_segment, day_int, hour_int,
                        profile["speed_min"] * hma, profile["speed_max"] * hma,
                        profile["accel"], profile["decel"], segment_dist_m, elapsed_s
                    ))
                except Exception as e:
                    logger.error(f"Failed starting DB task: {e}")

            app_state.state.current_segment_idx = seg_idx
            app_state.state.segment_entry_time = timestamp
        elif current_segment == -1:
            app_state.state.current_segment_idx = seg_idx
            app_state.state.segment_entry_time = timestamp

        etas = ml_estimator.get_etas(seg_idx, dist_covered, route_manager)
        
        # Save ETAs to state for new connections
        app_state.state.upcoming_etas = etas

        # Create broadcast dict
        return app_state.get_state_dict()
    except Exception as e:
        logger.error(f"Error processing payload: {e}")
        return None

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connected successfully to HiveMQ broker {BROKER}")
        client.subscribe(TOPIC)
        logger.info(f"Subscribed to topic: {TOPIC}")
    else:
        logger.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    logger.info(f"Received message on topic {msg.topic}")
    try:
        data = json.loads(msg.payload.decode())
        
        # Handle the custom types defined in the problem statement
        msg_type = data.get("type", "live")
        
        broadcast_msg = None
        
        if msg_type == "live":
            broadcast_msg = process_payload(data)
        elif msg_type == "batch":
            # For a batch, process the latest point, or process all. 
            # Processing the latest point is usually enough for real-time tracking
            batch_data = data.get("data", [])
            if batch_data:
                latest_point = batch_data[-1]
                broadcast_msg = process_payload(latest_point)
        elif msg_type == "recovery":
            # For recovery, we might just update to the "current" point or the last of history.
            current_payload = data.get("current")
            if current_payload:
                broadcast_msg = process_payload(current_payload)
        
        if broadcast_msg:
            # We need to run the async broadcast function in the event loop
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ws_manager.broadcast(broadcast_msg))
            except RuntimeError:
                # If there's no running event loop in this thread, we shouldn't fail silently
                pass 
            
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON payload")
    except Exception as e:
        logger.error(f"Error handling message: {e}")

def start_mqtt_client(loop):
    """
    Start the MQTT client.
    We pass the FastAPI event loop to handle WebSockets broadcasts.
    """
    client = mqtt.Client(client_id="fastapi_backend", clean_session=True)
    
    # Configure TLS for port 8883
    client.tls_set()
    
    # Set credentials
    client.username_pw_set(USERNAME, PASSWORD)
    
    client.on_connect = on_connect
    client.on_message = on_message
    
    # We will need the event loop inside on_message
    # Make loop available globally, or just let python handle it
    # Paho mqtt runs in its own thread, getting the loop there might be tricky,
    # so we might need a thread-safe way. We'll refine the broadcast logic.
    
    # Actually, asyncio.run_coroutine_threadsafe is best here.
    async def safe_broadcast(msg):
        await ws_manager.broadcast(msg)
        
    def thread_safe_on_message(client, userdata, msg):
        logger.info(f"Received message on topic {msg.topic}")
        try:
            data = json.loads(msg.payload.decode())
            broadcast_msg = None
            
            if isinstance(data, list):
                if data:
                    broadcast_msg = process_payload(data[-1])
            else:
                msg_type = data.get("type", "live")
                if msg_type == "live":
                    broadcast_msg = process_payload(data)
                elif msg_type == "batch":
                    batch_data = data.get("data", [])
                    if batch_data:
                        broadcast_msg = process_payload(batch_data[-1])
                elif msg_type == "recovery":
                    current_payload = data.get("current")
                    if current_payload:
                        broadcast_msg = process_payload(current_payload)
            
            if broadcast_msg:
                asyncio.run_coroutine_threadsafe(safe_broadcast(broadcast_msg), loop)
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    client.on_message = thread_safe_on_message
    
    try:
        client.connect(BROKER, PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        logger.error(f"MQTT Connection Error: {e}")

# This will be called from main.py on startup
