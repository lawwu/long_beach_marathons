#!/usr/bin/env python3
"""
Generate finish-time histograms from Long Beach Marathon result JSON files.

Usage examples:
    python src/plot_finish_histograms.py data/longbeach_2024.json
    python src/plot_finish_histograms.py data/longbeach_2024.json --gender-subevents "Long Beach Marathon" "Long Beach Half Marathon"
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib.pyplot as plt


def load_records(path: Path) -> Dict:
    """Load the JSON payload saved by download_longbeach_results.py."""
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def sanitize_filename(name: str) -> str:
    """Convert a subevent name into a filesystem-friendly slug."""
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    return slug or "unknown"


def minutes(chiptime_ms: int) -> float:
    """Convert chip time stored in milliseconds to minutes."""
    return chiptime_ms / 60000.0


def plot_histogram(
    times_ms: Sequence[int],
    *,
    title: str,
    output_path: Path,
    bins: int,
    color: str = "#1f77b4",
    label: Optional[str] = None,
) -> None:
    """Render and save a histogram for the provided times."""
    if not times_ms:
        return

    times_min = [minutes(t) for t in times_ms]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(times_min, bins=bins, color=color, edgecolor="white", alpha=0.75, label=label)
    ax.set_title(title)
    ax.set_xlabel("Chip Time (minutes)")
    ax.set_ylabel("Finishers")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.set_xlim(
        left=max(0, math.floor(min(times_min)) - 5),
        right=math.ceil(max(times_min)) + 5,
    )
    if label:
        ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_gender_histogram(
    male_times: Sequence[int],
    female_times: Sequence[int],
    *,
    title: str,
    output_path: Path,
    bins: int,
    men_label: str = "Men",
    women_label: str = "Women",
) -> None:
    """Render overlapping histograms for men and women finishers."""
    if not male_times and not female_times:
        return

    all_times = list(male_times) + list(female_times)
    times_min = [minutes(t) for t in all_times]
    fig, ax = plt.subplots(figsize=(8, 5))
    if male_times:
        ax.hist(
            [minutes(t) for t in male_times],
            bins=bins,
            color="#1f77b4",
            edgecolor="white",
            alpha=0.6,
            label=men_label,
        )
    if female_times:
        ax.hist(
            [minutes(t) for t in female_times],
            bins=bins,
            color="#ff7f0e",
            edgecolor="white",
            alpha=0.6,
            label=women_label,
        )
    ax.set_title(title)
    ax.set_xlabel("Chip Time (minutes)")
    ax.set_ylabel("Finishers")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.set_xlim(
        left=max(0, math.floor(min(times_min)) - 5),
        right=math.ceil(max(times_min)) + 5,
    )
    ax.legend()
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def collect_finishers(records: Iterable[Dict], subevent: str) -> List[int]:
    """Return chip times (ms) for finishers in the given subevent."""
    times: List[int] = []
    for rec in records:
        if rec.get("subevent") != subevent:
            continue
        chip = rec.get("chiptime")
        if chip and chip > 0:
            times.append(chip)
    return times


def collect_gender_finishers(records: Iterable[Dict], subevent: str) -> Dict[str, List[int]]:
    """Return chip times keyed by gender for the subevent."""
    buckets: Dict[str, List[int]] = {"M": [], "F": []}
    for rec in records:
        if rec.get("subevent") != subevent:
            continue
        chip = rec.get("chiptime")
        if chip and chip > 0:
            sex = rec.get("sex")
            if sex in buckets:
                buckets[sex].append(chip)
    return buckets


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plot finish-time histograms from race result JSON files.")
    parser.add_argument("input", type=Path, help="Path to JSON results (from download_longbeach_results.py)")
    parser.add_argument("--output-dir", type=Path, default=Path("plots"), help="Directory for generated plots")
    parser.add_argument(
        "--bins",
        type=int,
        default=40,
        help="Number of bins for standard histograms (default: 40)",
    )
    parser.add_argument(
        "--gender-bins",
        type=int,
        default=45,
        help="Number of bins for gender split histograms (default: 45)",
    )
    parser.add_argument(
        "--gender-subevents",
        nargs="*",
        default=[],
        help="Subevent names to plot with gender overlay (exact match)",
    )
    parser.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional subset of subevent names (exact match) to plot",
    )
    args = parser.parse_args(argv)

    payload = load_records(args.input)
    records = payload.get("records", [])
    subevents = sorted({rec.get("subevent") for rec in records if rec.get("subevent")})

    target_subevents = args.only if args.only else subevents
    for subevent in target_subevents:
        if not subevent:
            continue
        times = collect_finishers(records, subevent)
        if not times:
            continue
        slug = sanitize_filename(subevent)
        out_path = args.output_dir / f"{slug}_finish_times_hist.png"
        plot_histogram(times, title=f"{subevent} Finish Times", output_path=out_path, bins=args.bins)

    for subevent in args.gender_subevents:
        buckets = collect_gender_finishers(records, subevent)
        if not (buckets["M"] or buckets["F"]):
            continue
        slug = sanitize_filename(subevent)
        out_path = args.output_dir / f"{slug}_gender_finish_hist.png"
        plot_gender_histogram(
            buckets["M"],
            buckets["F"],
            title=f"{subevent} Finish Times by Sex",
            output_path=out_path,
            bins=args.gender_bins,
        )

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

