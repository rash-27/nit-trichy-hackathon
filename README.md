# 🚍 Resilient Public Transport Tracking

## 📌 Project Overview & Problem Significance

**The Problem:** Current transit tracking systems are brittle. They fail completely in environments with low bandwidth, high latency, or total signal loss (like tunnels or dead zones). This leaves commuters stranded staring at frozen maps, without accurate location data or reliable ETAs.

**Our Solution:** We built a lightweight, ultra-resilient tracking architecture that seamlessly handles network drops. It uses adaptive payloads, client-side predictive smoothing, and store-and-forward MQTT buffering to ensure the end-user never sees a broken map, even when the bus goes completely offline.


## 🛠️ Team's Approach (Core Engineering)

Our strategy focuses on 4 core pillars to guarantee resilience over standard HTTP-polling architectures:

### 1. Adaptive Update Frequency (Throttling)
Instead of flooding the network with heavy HTTP requests, our IoT bus simulator uses **MQTT**. On weak connections, it intelligently switches to a "Batch" mode, compressing 10 seconds of GPS pings into a single, tiny JSON payload to save bandwidth.

### 2. Predictive Smoothing (Dead Reckoning)
When a commuter's phone loses connection, the map doesn't freeze. Our React frontend uses a local **Watchdog Timer** and `Turf.js`. If the WebSocket goes silent, the UI visually inches the bus marker forward along the drawn route line based on its last known speed. **No teleporting, no frozen maps.**

### 3. Store-and-Forward Buffering
If the bus enters a tunnel and loses signal entirely, the IoT script buffers the GPS coordinates locally. Upon reconnection, it fires a massive **"Recovery Payload"** to the server. This ensures zero historical data is lost, keeping our ML training datasets perfectly intact.

### 4. Segment-Based ML ETA Prediction & Continuous Batch Training
Instead of complex, heavy Deep Learning, we utilize a lightweight Scikit-Learn `RandomForestRegressor`. It predicts segment-by-segment travel times based on time-of-day and historical traffic.
* **Solving the Cold Start:** Initialized with synthetic baseline data to provide Day 1 ETAs. 
* **The Retraining Loop:** As buses drive, real segment durations are autonomously logged into our SQLite database. A batch-retraining pipeline pulls this ground-truth data, retrains the model, and hot-swaps it into the live server to constantly reduce residual error.

**Model Performance Improvement (Before vs. After 1 Batch Training Cycle):**
<p align="center">
<img width="45%" height="350" alt="before-batch-training" src="https://github.com/user-attachments/assets/eb7c9b07-a082-4078-94bf-895dec3ea94a" />
<img width="45%" height="350" alt="after-batch-training" src="https://github.com/user-attachments/assets/929c52ff-3f05-4507-b9a2-b8b735a4bcd1" />
</p>

## 🏗️ System Architecture

Our architecture ensures a decoupled, linear data flow from the bus to the commuter.
<div align="center">
<img width="741" height="401" alt="final-archi" src="https://github.com/user-attachments/assets/7cc1799d-e0cc-4676-96b0-b8e41c785f55" />
</div>


* **Producer (Public Bus Simulator):** A Python script generating real-world OSRM-mapped coordinates and actively simulating network states (Normal, Throttled, Offline).
* **Message Broker:** HiveMQ (MQTT over TLS) handling Publish/Subscribe routing efficiently with QoS guarantees.
* **Backend & ML:** A FastAPI server that aggregates MQTT data, calculates live ETAs using the pre-trained Random Forest model, and broadcasts updates natively via WebSockets.
* **Database:** SQLite. *(Design Note: We intentionally swapped traditional PostgreSQL for SQLite to ensure seamless, zero-config embedded integration and lightning-fast batch training data storage during the tight 36-hour hackathon constraint).*
* **Consumer:** A React application connected via WebSockets to receive instant, fan-out updates with zero database-query overhead.

## 💻 Tech Stack

### Frontend
* **React.js & Vite**
* **Tailwind CSS**
* **Leaflet.js** (Low-bandwidth map rendering)
* **Turf.js** (Geospatial math & Dead Reckoning)

### Backend
* **Python 3 & FastAPI**
* **WebSockets**

### IoT & Messaging
* **MQTT Protocol**
* **HiveMQ Broker**
* **`paho-mqtt`**

### Machine Learning & Data
* **Scikit-Learn** (`RandomForestRegressor`)
* **Pandas**
* **SQLite**


## 🚀 Setup Instructions

Reproduce our project locally in minutes. 

### Step 1: Clone the Repository
```bash
git clone [https://github.com/rash-27/nit-trichy-hackathon.git](https://github.com/rash-27/nit-trichy-hackathon.git) resilient-transport-tracker
cd resilient-transport-tracker
```

### Step 2: Start the Backend & ML Server
```bash
cd server
python -m venv .venv 
source .venv/bin/activate
pip install -r requirements.txt

# Run the FastAPI server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 3: Start the Frontend (Consumer App)
Open a new terminal window:
```bash
cd fe
npm install  # or bun install
npm run dev  # or bun run dev
```

### Step 4: Run the Bus Simulator (Producer)
Open a third terminal window:
```bash
cd server
source .venv/bin/activate

# Start the IoT simulation
python bus_simulator.py
```
🎮 Live Demo Controls: Our simulator features a robust CLI to dynamically spawn buses and trigger time-bound network states live during the demo. While the simulator is running, use these commands:

    Type help + Enter ➡️ View all commands.

    Type add <bus_id> <route.csv> + Enter ➡️ Spawn a Bus: Starts publishing live GPS data for a specific bus (e.g., add bus_1 location.csv).

    Type <bus_id> -t <seconds> + Enter ➡️ Throttled Mode: Simulates a weak network for X seconds, batching payloads to save bandwidth before automatically recovering (e.g., bus_1 -t 15).

    Type <bus_id> -o <seconds> + Enter ➡️ Offline Mode: Simulates entering a tunnel/dead zone for X seconds. The bus goes completely silent, buffers data locally, and fires a massive recovery payload upon reconnection (e.g., bus_1 -o 10).
