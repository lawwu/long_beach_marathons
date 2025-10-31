#!/usr/bin/env python3
"""
Utilities for downloading Long Beach Marathon results from the Xact Results API.

The script fetches event metadata from the feeds API, then iterates the JSON
`search` endpoint to collect entrant records for the desired events. By default
it downloads all marathon-branded events for 2024 and earlier and stores them
under `data/longbeach_archive`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib import error, parse, request


FEEDS_URL = "https://feeds.xacte.com/metaeventconfig"
SEARCH_URL = "https://results.xacte.com/json/search"


def fetch_metaevent(metaevent_id: int) -> Dict:
    """Return the metaevent configuration payload."""
    url = f"{FEEDS_URL}?id={metaevent_id}"
    with request.urlopen(url) as resp:  # nosec: B310 - trusted upstream endpoint
        return json.load(resp)


def iter_events(metaevent: Dict) -> Iterable[Dict]:
    """Yield events from the metaevent payload."""
    for event in metaevent.get("event", []):
        yield event


def matches_event(event: Dict, *, min_year: Optional[int], max_year: Optional[int], name_filter: str) -> bool:
    """Return True if the event passes the configured filters."""
    date = event.get("eventdate", "")
    year = int(date[:4]) if date else 0
    if min_year is not None and year < min_year:
        return False
    if max_year is not None and year > max_year:
        return False
    name = event.get("name", "")
    if name_filter and name_filter.lower() not in name.lower():
        return False
    return True


def fetch_results(event_id: int, *, limit: int = 1000, retry: int = 3, backoff: float = 1.0) -> Dict:
    """
    Download all entrant records for `event_id`.

    Returns a dictionary with `records`, `total`, and metadata.
    """
    params: Dict[str, int] = {
        "eventId": event_id,
        "subeventId": -1,
        "order": "bib",
        "limit": limit,
        "offset": 0,
    }
    all_records: List[Dict] = []
    total_records: Optional[int] = None

    while True:
        url = f"{SEARCH_URL}?{parse.urlencode(params)}"
        try:
            with request.urlopen(url) as resp:  # nosec: B310 - trusted upstream endpoint
                payload = json.load(resp)
        except error.URLError as exc:
            if retry <= 0:
                raise RuntimeError(f"Failed to fetch event {event_id}: {exc}") from exc
            time.sleep(backoff)
            retry -= 1
            backoff *= 2
            continue

        batch = payload.get("aaData", [])
        all_records.extend(batch)

        if total_records is None:
            total_records = payload.get("iTotalRecords", len(batch))

        params["offset"] += limit
        if not batch or (total_records is not None and len(all_records) >= total_records):
            break

    if total_records is None:
        raise RuntimeError(f"No data returned for event {event_id}")

    return {
        "eventId": event_id,
        "total": total_records,
        "fetched": len(all_records),
        "records": all_records,
    }


def save_payload(payload: Dict, destination: Path, *, year: Optional[int], name: str) -> None:
    """Write the event payload (plus metadata) to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    blob = dict(payload)
    blob.update({"year": year, "name": name})
    with destination.open("w", encoding="utf-8") as fh:
        json.dump(blob, fh)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metaevent-id",
        type=int,
        default=744,
        help="Metaevent identifier (default: 744 for Long Beach Marathon)",
    )
    parser.add_argument(
        "--min-year",
        type=int,
        help="Earliest event year to download",
    )
    parser.add_argument(
        "--max-year",
        type=int,
        default=2024,
        help="Latest event year to download (default: 2024)",
    )
    parser.add_argument(
        "--name-filter",
        default="marathon",
        help="Substring filter applied to event name (default: 'marathon')",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/longbeach_archive"),
        help="Directory for output JSON files",
    )
    parser.add_argument(
        "--prefix",
        default="longbeach",
        help="Filename prefix for saved JSON files (default: longbeach)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Page size for API pagination (default: 1000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching events without downloading results",
    )
    args = parser.parse_args(argv)

    metaevent = fetch_metaevent(args.metaevent_id)
    selected_events: List[Dict] = []
    for event in iter_events(metaevent):
        if matches_event(event, min_year=args.min_year, max_year=args.max_year, name_filter=args.name_filter):
            selected_events.append(event)

    if not selected_events:
        print("No matching events found", file=sys.stderr)
        return 1

    for event in sorted(selected_events, key=lambda e: e.get("eventdate", ""), reverse=True):
        event_id = event["id"]
        year = int(event["eventdate"][:4])
        name = event.get("name", "")
        output_path = args.output_dir / f"{args.prefix}_{year}.json"

        if args.dry_run:
            print(f"[dry-run] {year} - eventId {event_id} -> {output_path}")
            continue

        payload = fetch_results(event_id, limit=args.limit)
        save_payload(payload, output_path, year=year, name=name)
        print(f"Saved {payload['fetched']} records for {year} ({event_id}) to {output_path}")

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

