"""GeoNames Offline City Gazetteer Service.

Provides 100% offline reverse geocoding fallback for GPS coordinates.
Supports loading from `data/geonames/cities500.txt` (or bundled gazetteer)
and uses Haversine distance to locate the nearest city/place.
"""

from __future__ import annotations

import csv
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Earth radius in kilometers
EARTH_RADIUS_KM = 6371.0

@dataclass(slots=True)
class GeoCity:
    name: str
    country: str
    admin1: str  # State / Province
    latitude: float
    longitude: float
    population: int = 0

# Bundled fallback gazetteer of major cities and parks across the globe
EMBEDDED_CITIES: List[Tuple[str, str, str, float, float, int]] = [
    # North America
    ("Yosemite National Park", "United States", "California", 37.8651, -119.5383, 5000),
    ("Lake Tahoe", "United States", "California", 39.0968, -120.0324, 25000),
    ("Austin", "United States", "Texas", 30.2672, -97.7431, 960000),
    ("San Francisco", "United States", "California", 37.7749, -122.4194, 870000),
    ("Los Angeles", "United States", "California", 34.0522, -118.2437, 3900000),
    ("New York City", "United States", "New York", 40.7128, -74.0060, 8300000),
    ("Seattle", "United States", "Washington", 47.6062, -122.3321, 740000),
    ("Chicago", "United States", "Illinois", 41.8781, -87.6298, 2700000),
    ("Denver", "United States", "Colorado", 39.7392, -104.9903, 715000),
    ("Miami", "United States", "Florida", 25.7617, -80.1918, 442000),
    ("Orlando", "United States", "Florida", 28.5383, -81.3792, 307000),
    ("Lake Buena Vista", "United States", "Florida", 28.3772, -81.5707, 10000),
    ("Toronto", "Canada", "Ontario", 43.6532, -79.3832, 2930000),
    ("Vancouver", "Canada", "British Columbia", 49.2827, -123.1207, 675000),
    
    # Europe
    ("London", "United Kingdom", "England", 51.5074, -0.1278, 8982000),
    ("Paris", "France", "Île-de-France", 48.8566, 2.3522, 2161000),
    ("Rome", "Italy", "Lazio", 41.9028, 12.4964, 2873000),
    ("Berlin", "Germany", "Berlin", 52.5200, 13.4050, 3645000),
    ("Madrid", "Spain", "Madrid", 40.4168, -3.7038, 3223000),
    ("Amsterdam", "Netherlands", "North Holland", 52.3676, 4.9041, 821000),
    ("Zurich", "Switzerland", "Zurich", 47.3769, 8.5417, 402000),
    
    # Asia & Oceania
    ("Tokyo", "Japan", "Tokyo", 35.6762, 139.6503, 13960000),
    ("Kyoto", "Japan", "Kyoto", 35.0116, 135.7681, 1464000),
    ("Singapore", "Singapore", "Singapore", 1.3521, 103.8198, 5686000),
    ("Sydney", "Australia", "New South Wales", -33.8688, 151.2093, 5312000),
    ("Melbourne", "Australia", "Victoria", -37.8136, 144.9631, 5078000),
    ("Delhi", "India", "Delhi", 28.6139, 77.2090, 16787000),
    ("Mumbai", "India", "Maharashtra", 19.0760, 72.8777, 12442000),
    ("Bangalore", "India", "Karnataka", 12.9716, 77.5946, 8443000),
    ("Ludhiana", "India", "Punjab", 30.9010, 75.8573, 1618000),
    ("Khanna", "India", "Punjab", 30.7067, 76.2198, 128000),
    ("Dubai", "United Arab Emirates", "Dubai", 25.2048, 55.2708, 3331000),
]

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in km."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_KM * c

class GeoNamesService:
    def __init__(self, geonames_dir: Path = Path("data/geonames")) -> None:
        self.geonames_dir = geonames_dir
        self.cities: List[GeoCity] = []
        self._load_gazetteer()

    def _load_gazetteer(self) -> None:
        """Load external GeoNames cities500 file or fallback to embedded dataset."""
        loaded_count = 0
        cities_file = self.geonames_dir / "cities500.txt"

        if cities_file.is_file():
            try:
                with cities_file.open("r", encoding="utf-8") as f:
                    reader = csv.reader(f, delimiter="\t")
                    for row in reader:
                        if len(row) >= 15:
                            # GeoNames TSV columns: 1: name, 4: lat, 5: lon, 8: country, 10: admin1, 14: population
                            try:
                                name = row[1]
                                lat = float(row[4])
                                lon = float(row[5])
                                country = row[8]
                                admin1 = row[10]
                                pop = int(row[14]) if row[14].isdigit() else 0
                                self.cities.append(GeoCity(name=name, country=country, admin1=admin1, latitude=lat, longitude=lon, population=pop))
                                loaded_count += 1
                            except (ValueError, IndexError):
                                continue
                logger.info("Loaded %d cities from %s", loaded_count, cities_file)
            except Exception as e:
                logger.warning("Could not read %s, using embedded gazetteer: %s", cities_file, e)

        if not self.cities:
            for name, country, admin1, lat, lon, pop in EMBEDDED_CITIES:
                self.cities.append(GeoCity(name=name, country=country, admin1=admin1, latitude=lat, longitude=lon, population=pop))
            logger.info("Loaded %d embedded fallback cities", len(self.cities))

    def find_nearest_city(self, latitude: float, longitude: float, max_dist_km: float = 300.0) -> Optional[Dict[str, Any]]:
        """Find the nearest city to given latitude and longitude within max_dist_km."""
        if not self.cities:
            return None

        best_city: Optional[GeoCity] = None
        min_distance = float("inf")

        for city in self.cities:
            dist = haversine_km(latitude, longitude, city.latitude, city.longitude)
            if dist < min_distance:
                min_distance = dist
                best_city = city

        if best_city and min_distance <= max_dist_km:
            confidence = max(50, min(95, int(100 - (min_distance / max_dist_km) * 40)))
            return {
                "city": best_city.name,
                "state": best_city.admin1,
                "country": best_city.country,
                "place_name": f"{best_city.name}, {best_city.admin1}, {best_city.country}" if best_city.admin1 else f"{best_city.name}, {best_city.country}",
                "distance_km": round(min_distance, 1),
                "source": "geonames",
                "confidence": confidence,
            }

        return None
