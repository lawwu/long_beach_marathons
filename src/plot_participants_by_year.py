#!/usr/bin/env python3
"""
Plot annual participant counts for the Long Beach Marathon and Half Marathon.

The script expects the JSON files produced by `download_longbeach_results.py`
and aggregates entrant counts for marathon- and half-branded subevents. The
resulting line chart is saved to the plots directory by default.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (after backend selection)


DEFAULT_INCLUDE = [
    Path("data/longbeach_2025.json"),
    Path("data/longbeach_2025_runners.json"),
]


def iter_result_files(archive_dir: Path, extra_files: Iterable[Path]) -> Iterable[Path]:
    """Yield JSON result files from the archive directory plus any extras."""
    seen = set()
    for path in sorted(archive_dir.glob("longbeach_*.json")):
        seen.add(path.resolve())
        yield path
    for path in sorted(extra_files):
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            continue
        seen.add(resolved)
        yield path


def infer_year(path: Path, data: Dict) -> int | None:
    """Determine the event year from JSON metadata or filename."""
    year = data.get("year")
    if year is not None:
        return int(year)
    match = re.search(r"(20\\d{2}|19\\d{2})", path.stem)
    if match:
        return int(match.group(1))
    return None


def load_counts(path: Path) -> Tuple[int | None, Dict[str, int]]:
    """Return (year, counts) pair for the specified result JSON."""
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    records = data.get("records", [])
    year = infer_year(path, data)
    if year is None:
        raise ValueError(f"Unable to determine year for {path}")
    counts = {"marathon": 0, "half": 0}
    for rec in records:
        subevent = (rec.get("subevent") or "").lower()
        if "marathon" in subevent and "half" not in subevent and "5k" not in subevent and "chair half" not in subevent and "tandem" not in subevent:
            counts["marathon"] += 1
        elif "half" in subevent and "5k" not in subevent:
            counts["half"] += 1
    counts["total"] = counts["marathon"] + counts["half"]
    return year, counts


def build_series(files: Iterable[Path]) -> Tuple[List[int], List[int], List[int], List[int]]:
    """Return lists of years, marathon counts, half counts, and totals."""
    years: List[int] = []
    marathon_counts: List[int] = []
    half_counts: List[int] = []
    total_counts: List[int] = []

    for path in files:
        year, counts = load_counts(path)
        if year is None:
            continue
        years.append(int(year))
        marathon_counts.append(counts["marathon"])
        half_counts.append(counts["half"])
        total_counts.append(counts["total"])

    order = sorted(range(len(years)), key=lambda idx: years[idx])
    years = [years[idx] for idx in order]
    marathon_counts = [marathon_counts[idx] for idx in order]
    half_counts = [half_counts[idx] for idx in order]
    total_counts = [total_counts[idx] for idx in order]
    return years, marathon_counts, half_counts, total_counts


def plot_series(years: List[int], marathon_counts: List[int], half_counts: List[int], total_counts: List[int], *, output: Path) -> None:
    """Plot the participant trends and save to `output`."""
    if not years:
        raise ValueError("No data available to plot")

    plt.figure(figsize=(9, 5))
    plt.plot(years, marathon_counts, marker="o", label="Marathon")
    plt.plot(years, half_counts, marker="o", label="Half Marathon")
    plt.plot(years, total_counts, marker="o", label="Total (Marathon + Half)")
    plt.title("Long Beach Marathon vs Half Marathon Participants")
    plt.xlabel("Year")
    plt.ylabel("Entrants")
    plt.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    plt.legend()
    plt.xticks(years, rotation=45)
    plt.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=150)
    plt.close()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("data/longbeach_archive"),
        help="Directory containing archived JSON results (default: data/longbeach_archive)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("plots/longbeach_participants_by_year.png"),
        help="Destination for the generated plot",
    )
    parser.add_argument(
        "--include",
        type=Path,
        nargs="*",
        default=None,
        help="Additional JSON files to include (e.g., current-year dataset)",
    )
    parser.add_argument(
        "--print-table",
        action="store_true",
        help="Print the year-by-year counts instead of or in addition to plotting",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip generating the PNG (useful for quick tabular checks)",
    )
    args = parser.parse_args(argv)

    include_files = args.include if args.include is not None else DEFAULT_INCLUDE
    files = list(iter_result_files(args.archive_dir, include_files))
    years, marathon_counts, half_counts, total_counts = build_series(files)

    if args.print_table:
        print("Year | Marathon | Half Marathon | Total")
        print("---- | -------- | ------------- | -----")
        for year, m, h, t in zip(years, marathon_counts, half_counts, total_counts):
            print(f"{year} | {m} | {h} | {t}")

    if not args.no_plot:
        plot_series(years, marathon_counts, half_counts, total_counts, output=args.output)
        print(f"Saved plot to {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
