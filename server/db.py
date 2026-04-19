import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "metrics.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS segment_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL,
                bus_id TEXT,
                segment_id INTEGER,
                day_of_week INTEGER,
                hour_of_day INTEGER,
                speed_min REAL,
                speed_max REAL,
                accel REAL,
                decel REAL,
                segment_distance_m REAL,
                actual_travel_time_seconds REAL
            )
        ''')
        await db.commit()

async def insert_segment_time(timestamp, bus_id, segment_id, day, hour, s_min, s_max, accel, decel, dist_m, time_elapsed):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO segment_times 
                (timestamp, bus_id, segment_id, day_of_week, hour_of_day, speed_min, speed_max, accel, decel, segment_distance_m, actual_travel_time_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, bus_id, segment_id, day, hour, s_min, s_max, accel, decel, dist_m, time_elapsed))
            await db.commit()
    except Exception as e:
        print(f"Error inserting segment time: {e}")
