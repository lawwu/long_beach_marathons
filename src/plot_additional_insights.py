#!/usr/bin/env python3
"""
Generate a set of more detailed Long Beach Marathon insights:

1. Stacked gender composition per year for marathon and half marathon entrants.
2. Median marathon finish times by gender (men vs women) across years.
3. 2025 marathon age distributions (histogram + age vs finish scatter).

The script expects the JSON files produced by `download_longbeach_results.py`
to be present under `data/longbeach_archive/`, plus the 2025 dataset in either
`data/longbeach_2025.json` or `data/longbeach_2025_runners.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Default file pattern coverage (2025 may live outside archive folder originally)
DEFAULT_INCLUDE = [
    Path("data/longbeach_2025.json"),
    Path("data/longbeach_2025_runners.json"),
]


def load_json(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def infer_year(path: Path, data: Dict) -> int | None:
    year = data.get("year")
    if year is not None:
        return int(year)
    match = re.search(r"(19|20)\\d{2}", path.stem)
    if match:
        return int(match.group(0))
    return None


def classify_race(subevent: str) -> str | None:
    label = subevent.lower()
    if "half" in label and "5k" not in label:
        return "half"
    if "marathon" in label and "half" not in label and "5k" not in label and "chair half" not in label and "tandem" not in label:
        return "marathon"
    return None


def gather_files(archive_dir: Path, extras: Iterable[Path]) -> List[Path]:
    seen = set()
    files: List[Path] = []

    for path in sorted(archive_dir.glob("longbeach_*.json")):
        resolved = path.resolve()
        seen.add(resolved)
        files.append(path)

    for extra in sorted(extras):
        if not extra.exists():
            continue
        resolved = extra.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(extra)

    return files


def to_minutes(chip_ms: int) -> float:
    return chip_ms / 60000.0


def collect_metrics(files: Iterable[Path]) -> Tuple[
    Dict[int, Dict[str, Dict[str, int]]],
    Dict[int, Dict[str, List[int]]],
    Dict[str, List[int]],
]:
    """
    Return:
      - yearly gender counts by race type
      - yearly marathon chip times by gender
      - per-gender chip times for the 2025 marathon
    """
    gender_counts = defaultdict(lambda: {"marathon": defaultdict(int), "half": defaultdict(int)})
    marathon_times = defaultdict(lambda: defaultdict(list))
    marathon_2025_times = defaultdict(list)
    marathon_2025_ages = defaultdict(list)

    for path in files:
        data = load_json(path)
        year = infer_year(path, data)
        if year is None:
            # If the filename contains "runners" we treat it as supplementary and skip.
            if "runners" in path.stem:
                continue
            raise ValueError(f"Unable to determine year for {path}")

        for rec in data.get("records", []):
            subevent = rec.get("subevent") or ""
            race = classify_race(subevent)
            if race is None:
                continue

            sex = rec.get("sex") or "Unknown"
            chip = rec.get("chiptime")

            gender_counts[year][race][sex] += 1

            if chip and chip > 0 and race == "marathon":
                marathon_times[year][sex].append(chip)
                if year == 2025:
                    marathon_2025_times[sex].append(chip)
                    age = rec.get("age")
                    if age is not None:
                        marathon_2025_ages[sex].append((age, chip))

    return gender_counts, marathon_times, {"times": marathon_2025_times, "ages": marathon_2025_ages}


def plot_gender_composition(gender_counts: Dict[int, Dict[str, Dict[str, int]]], output_dir: Path) -> None:
    years = sorted(gender_counts.keys())
    sexes = ["M", "F", "O", "Unknown"]

    def build_stack(race_type: str) -> None:
        fig, ax = plt.subplots(figsize=(10, 5))
        bottom = [0] * len(years)
        for sex in sexes:
            values = [gender_counts[year][race_type].get(sex, 0) for year in years]
            if all(v == 0 for v in values):
                continue
            ax.bar(years, values, bottom=bottom, label=sex)
            bottom = [b + v for b, v in zip(bottom, values)]

        ax.set_title(f"{race_type.capitalize()} Entrants by Gender")
        ax.set_xlabel("Year")
        ax.set_ylabel("Entrants")
        ax.legend()
        ax.grid(alpha=0.3, linestyle="--", linewidth=0.5, axis="y")
        ax.set_xticks(years)
        ax.set_xticklabels(years, rotation=45)
        fig.tight_layout()
        output = output_dir / f"{race_type}_gender_stack.png"
        fig.savefig(output, dpi=150)
        plt.close(fig)

    plot_gender_composition.marathon_path = output_dir / "marathon_gender_stack.png"  # type: ignore[attr-defined]
    plot_gender_composition.half_path = output_dir / "half_gender_stack.png"  # type: ignore[attr-defined]
    plot_gender_composition.timeseries_years = years  # type: ignore[attr-defined]

    build_stack("marathon")
    build_stack("half")


def plot_marathon_median_times(marathon_times: Dict[int, Dict[str, List[int]]], output_dir: Path) -> None:
    years = sorted(marathon_times.keys())
    men = []
    women = []

    for year in years:
        men_times = marathon_times[year].get("M")
        women_times = marathon_times[year].get("F")
        men.append(to_minutes(median(men_times)) if men_times else math.nan)
        women.append(to_minutes(median(women_times)) if women_times else math.nan)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(years, men, marker="o", label="Men")
    ax.plot(years, women, marker="o", label="Women")
    ax.set_title("Marathon Median Finish Time by Gender")
    ax.set_xlabel("Year")
    ax.set_ylabel("Median Chip Time (minutes)")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.legend()
    ax.set_xticks(years)
    ax.set_xticklabels(years, rotation=45)
    fig.tight_layout()
    output = output_dir / "marathon_median_finish_time.png"
    fig.savefig(output, dpi=150)
    plt.close(fig)


def plot_2025_age_distributions(marathon_2025: Dict[str, Dict], output_dir: Path) -> None:
    times = marathon_2025["times"]
    ages = marathon_2025["ages"]

    if not times:
        return

    # Histogram by gender
    fig, ax = plt.subplots(figsize=(8, 5))
    for sex, chip_list in times.items():
        if not chip_list:
            continue
        ax.hist(
            [to_minutes(t) for t in chip_list],
            bins=40,
            alpha=0.6,
            edgecolor="white",
            label=sex,
        )
    ax.set_title("2025 Marathon Finish Time Distribution by Gender")
    ax.set_xlabel("Chip Time (minutes)")
    ax.set_ylabel("Finishers")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "2025_marathon_finish_hist.png", dpi=150)
    plt.close(fig)

    # Age vs finish scatter plot
    fig, ax = plt.subplots(figsize=(8, 5))
    markers = {"M": "o", "F": "s", "O": "^", "Unknown": "x"}
    colors = {"M": "#1f77b4", "F": "#ff7f0e", "O": "#2ca02c", "Unknown": "#7f7f7f"}
    for sex, points in ages.items():
        if not points:
            continue
        xs = [age for age, _ in points]
        ys = [to_minutes(chip) for _, chip in points]
        ax.scatter(xs, ys, alpha=0.6, label=sex, marker=markers.get(sex, "o"), color=colors.get(sex, "#333333"))
    ax.set_title("2025 Marathon Finish Time vs Age")
    ax.set_xlabel("Age")
    ax.set_ylabel("Chip Time (minutes)")
    ax.grid(alpha=0.3, linestyle="--", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "2025_marathon_age_vs_finish.png", dpi=150)
    plt.close(fig)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("data/longbeach_archive"),
        help="Directory containing archived JSON files",
    )
    parser.add_argument(
        "--include",
        type=Path,
        nargs="*",
        default=None,
        help="Additional result JSON files to include",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("plots"),
        help="Destination for generated plots",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip plot creation (useful for dry-run checks)",
    )
    args = parser.parse_args(argv)

    include_files = args.include if args.include is not None else DEFAULT_INCLUDE
    files = gather_files(args.archive_dir, include_files)

    if not files:
        raise SystemExit("No result files found. Run download_longbeach_results.py first.")

    gender_counts, marathon_times, marathon_2025 = collect_metrics(files)

    if args.no_plot:
        print("Files included:")
        for path in files:
            print(f" - {path}")
        print("Years covered:", sorted(gender_counts.keys()))
        return 0

    args.output_dir.mkdir(parents=True, exist_ok=True)

    plot_gender_composition(gender_counts, args.output_dir)
    plot_marathon_median_times(marathon_times, args.output_dir)
    plot_2025_age_distributions(marathon_2025, args.output_dir)
    print(f"Charts saved to {args.output_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
