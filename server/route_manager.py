import math
import os
import csv

STOPS = [
    {"name": "Lanka Gate", "lat": 25.277768, "lng": 83.002231},
    {"name": "Stop -1", "lat": 25.263755, "lng": 82.997520},
    {"name": "Hyderabad Gate", "lat": 25.262927, "lng": 82.981793},
    {"name": "Rajeev Nagar Colony", "lat": 25.275039, "lng": 82.984572},
]

ROW_SPACING_M = 10

def flat_dist(lat1, lng1, lat2, lng2) -> float:
    """Distance in metres using flat-earth approx."""
    dlat = (lat2 - lat1) * 111320
    dlng = (lng2 - lng1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat * dlat + dlng * dlng)

class RouteManager:
    def __init__(self):
        self.stops = STOPS
        self.csv_path = os.path.join(os.path.dirname(__file__), "..", "location.csv")
        self.rows = []
        self._load_csv()
        
        # Precompute segment boundaries based on nearest row
        self.stop_indices = []
        for stop in self.stops:
            best_i, best_d = 0, float("inf")
            for i, (rlat, rlng) in enumerate(self.rows):
                d = flat_dist(rlat, rlng, stop["lat"], stop["lng"])
                if d < best_d:
                    best_i, best_d = i, d
            self.stop_indices.append(best_i)
            
        self.segments = []
        n_stops = len(self.stops)
        for i in range(n_stops):
            start_idx = self.stop_indices[i]
            end_idx = self.stop_indices[(i + 1) % n_stops]
            name = f"Segment-{i}"
            
            if end_idx > start_idx:
                n_rows = end_idx - start_idx
            else:
                n_rows = (len(self.rows) - start_idx) + end_idx
                
            distance_km = (n_rows * ROW_SPACING_M) / 1000.0
            
            self.segments.append({
                "segment_id": i,
                "name": name,
                "start_idx": int(start_idx),
                "end_idx": int(end_idx),
                "total_distance_km": float(distance_km),
                "end_stop_name": self.stops[(i+1)%n_stops]["name"]
            })

    def _load_csv(self):
        if not os.path.exists(self.csv_path):
            self.csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "campus_route.csv")
            if not os.path.exists(self.csv_path):
                self.csv_path = "location.csv"
        try:
            with open(self.csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                fields = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
                lat_col = "latitude" if "latitude" in fields else "lat"
                lng_col = "longitude" if "longitude" in fields else "lng"
                
                for row in reader:
                    self.rows.append((float(row[lat_col]), float(row[lng_col])))
        except Exception as e:
            print(f"Error loading route CSV: {e}")

    def get_current_segment_and_progress(self, current_lat, current_lng):
        if not self.rows:
            return 0, 0.0
            
        # Find exact or nearest row for current coord
        best_i, best_d = 0, float("inf")
        for i, (rlat, rlng) in enumerate(self.rows):
            d = flat_dist(rlat, rlng, current_lat, current_lng)
            if d < best_d:
                best_i, best_d = i, d
                
        # Find which segment best_i belongs to
        n_stops = len(self.stop_indices)
        for i in range(n_stops):
            start_idx = int(self.stop_indices[i])
            end_idx = int(self.stop_indices[(i + 1) % n_stops])
            
            is_in_segment = False
            if start_idx < end_idx:
                is_in_segment = start_idx <= best_i < end_idx
            else:
                is_in_segment = best_i >= start_idx or best_i < end_idx
                
            if is_in_segment:
                if best_i >= start_idx:
                    dist_rows = best_i - start_idx
                else:
                    dist_rows = (len(self.rows) - start_idx) + best_i
                    
                dist_covered_km = (float(dist_rows) * ROW_SPACING_M) / 1000.0
                return i, dist_covered_km
                
        return 0, 0.0

    def get_upcoming_stops(self, current_segment_idx):
        upcoming = []
        for i in range(current_segment_idx, len(self.segments)):
            upcoming.append({
                "segment_idx": i,
                "stop_name": self.segments[i].get('end_stop_name', 'Unknown')
            })
        return upcoming

route_manager = RouteManager()
