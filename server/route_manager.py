import math

STOPS = [
    {"name": "Lanka Gate", "lat": 25.277768, "lng": 83.002231},
    {"name": "Stop -1", "lat": 25.263755, "lng": 82.997520},
    {"name": "Hyderabad Gate", "lat": 25.262927, "lng": 82.981793},
    {"name": "Rajeev Nagar Colony", "lat": 25.275039, "lng": 82.984572},
    {"name": "Lanka Gate Return", "lat": 25.277768, "lng": 83.002231}
]

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees)
    """
    R = 6371.0 # Radius of earth in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

class RouteManager:
    def __init__(self):
        self.stops = STOPS
        self.segments = []
        for i in range(len(self.stops) - 1):
            segment_dist = haversine(
                self.stops[i]['lat'], self.stops[i]['lng'],
                self.stops[i+1]['lat'], self.stops[i+1]['lng']
            )
            self.segments.append({
                "segment_id": i,
                "start": self.stops[i],
                "end": self.stops[i+1],
                "total_distance_km": segment_dist
            })

    def get_current_segment_and_progress(self, current_lat, current_lng):
        """
        Naive approach: Find the segment where the distance between start->current + current->end 
        is closest to start->end. Or simply find the closest segment start, but since it's a loop,
        we can just check the closest line segment.
        For simplicity in this mock, we just find the closest segment sequentially that has not been fully traversed,
        or just the one where current point is located.
        Better approach: just find the distance of current_point to all line segments and pick min.
        """
        min_diff = float('inf')
        current_segment_idx = 0
        dist_covered_km = 0

        for idx, seg in enumerate(self.segments):
            d1 = haversine(seg['start']['lat'], seg['start']['lng'], current_lat, current_lng)
            d2 = haversine(current_lat, current_lng, seg['end']['lat'], seg['end']['lng'])
            diff = abs((d1 + d2) - seg['total_distance_km'])
            
            if diff < min_diff:
                min_diff = diff
                current_segment_idx = idx
                dist_covered_km = d1

        return current_segment_idx, dist_covered_km

    def get_upcoming_stops(self, current_segment_idx):
        upcoming = []
        for i in range(current_segment_idx, len(self.segments)):
            upcoming.append({
                "segment_idx": i,
                "stop_name": self.segments[i]['end']['name']
            })
        return upcoming

route_manager = RouteManager()
