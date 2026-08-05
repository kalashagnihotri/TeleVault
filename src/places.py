import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class PlaceConfig:
    label: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return (self.min_lat <= lat <= self.max_lat) and (self.min_lon <= lon <= self.max_lon)

class PlaceResolver:
    def __init__(self, config_path: Path = Path("config/places.json")) -> None:
        self.places: list[PlaceConfig] = []
        if config_path.is_file():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        self.places.append(
                            PlaceConfig(
                                label=item["label"],
                                min_lat=item["min_lat"],
                                max_lat=item["max_lat"],
                                min_lon=item["min_lon"],
                                max_lon=item["max_lon"],
                            )
                        )
                logger.info("Loaded %s custom offline places.", len(self.places))
            except Exception as e:
                logger.error("Failed to load places config from %r: %s", str(config_path), e)

    def resolve(self, lat: float | None, lon: float | None) -> str:
        if lat is None or lon is None:
            return "Misc"
            
        for place in self.places:
            if place.contains(lat, lon):
                return place.label
                
        return "Unknown GPS Location"
