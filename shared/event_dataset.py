import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATHS = [
    PROJECT_ROOT / "dataset" / "all_events_final.json",
    PROJECT_ROOT / "all_events_final.json",
]


@lru_cache(maxsize=1)
def load_event_dataset() -> list[dict]:
    for path in DATASET_PATHS:
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            for key in ("events", "items", "data", "results"):
                candidate = data.get(key)
                if isinstance(candidate, list):
                    return candidate
            return [data]

    raise FileNotFoundError(
        "Could not find all_events_final.json in dataset/ or the project root"
    )


def parse_event_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    return None


def normalize_event_record(event: dict) -> dict:
    return {
        "source": event.get("source"),
        "url": event.get("url"),
        "name": event.get("name"),
        "description": event.get("description"),
        "category": event.get("category"),
        "location": event.get("location"),
        "country": event.get("country"),
        "event_date": parse_event_date(event.get("date")),
        "speakers": event.get("speakers") or [],
        "exhibitors": event.get("exhibitors") or [],
        "ticket_price": event.get("ticket_price") or [],
        "expected_turnaround": event.get("expected_turnaround"),
        "domain": event.get("category"),
        "topic": event.get("name"),
        "geography": event.get("country"),
        "city": event.get("location"),
        "website": event.get("url"),
        "raw_event": event,
    }