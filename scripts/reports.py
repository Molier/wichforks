#!/usr/bin/env python3
"""Validate and aggregate community experience reports.

Usage:
    python -I scripts/reports.py validate
    python -I scripts/reports.py render
    python -I scripts/reports.py render --out /tmp/REPORTS.md

Reports live in data/reports/*.json and use the schema documented in
data/reports/README.md. Render rewrites docs/REPORTS.md; commit the result.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import date as date_cls
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS_RANK = {"perfect": 3, "playable": 2, "broken": 1, "wont-boot": 0}
STATUS_LABEL = {
    "perfect": "Perfect",
    "playable": "Playable",
    "broken": "Broken",
    "wont-boot": "Won't boot",
}
REQUIRED_FIELDS = (
    "fork_id",
    "build",
    "date",
    "game",
    "platform",
    "cpu",
    "gpu",
    "ram_gb",
    "status",
    "reporter",
)
FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9][a-z0-9-]*\.json$")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_forks(path: Path) -> dict[str, dict]:
    """Projects a report may name: forks, plus native ports from ports.json."""
    data = load_json(path)
    projects = {fork["id"]: fork for fork in data.get("forks", [])}
    ports_path = path.with_name("ports.json")
    if ports_path.exists():
        for port in load_json(ports_path).get("ports", []):
            projects.setdefault(port["id"], port)
    return projects


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_report(path: Path, report, fork_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["top-level JSON value must be an object"]

    for field in REQUIRED_FIELDS:
        value = report.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing required field: {field}")

    for field in ("fork_id", "build", "game", "platform", "cpu", "gpu", "reporter"):
        value = report.get(field)
        if value is not None and not isinstance(value, str):
            errors.append(f"{field} must be a string")

    fork_id = report.get("fork_id")
    if isinstance(fork_id, str) and fork_id not in fork_ids:
        errors.append(f"unknown fork_id: {fork_id}")

    match = FILENAME_RE.match(path.name)
    if not match:
        errors.append("filename must look like YYYY-MM-DD-<fork-id>-<slug>.json")

    raw_date = report.get("date")
    if isinstance(raw_date, str):
        try:
            date_cls.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"date must be YYYY-MM-DD, got: {raw_date}")
        else:
            if match and match.group(1) != raw_date:
                errors.append("filename date does not match the date field")

    status = report.get("status")
    if isinstance(status, str) and status not in STATUS_RANK:
        errors.append(f"status must be one of: {', '.join(STATUS_RANK)}")

    ram = report.get("ram_gb")
    if ram is not None and (not is_int(ram) or not 1 <= ram <= 2048):
        errors.append("ram_gb must be an integer between 1 and 2048")

    fps = report.get("fps_typical")
    if fps is not None and (not is_int(fps) or not 0 <= fps <= 360):
        errors.append("fps_typical must be an integer between 0 and 360")

    issues = report.get("issues")
    if issues is not None and (
        not isinstance(issues, list) or not all(isinstance(item, str) for item in issues)
    ):
        errors.append("issues must be an array of strings")

    source = report.get("source_url")
    if source is not None and (
        not isinstance(source, str) or not source.startswith(("http://", "https://"))
    ):
        errors.append("source_url must start with http:// or https://")

    return errors


def iter_report_paths(reports_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(reports_dir.glob("*.json"))
        if not path.name.startswith(("_", "."))
    ]


def load_reports(reports_dir: Path, fork_ids: set[str]) -> tuple[list[dict], list[str]]:
    reports: list[dict] = []
    problems: list[str] = []
    for path in iter_report_paths(reports_dir):
        try:
            report = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: {exc}")
            continue
        errors = validate_report(path, report, fork_ids)
        if errors:
            problems.extend(f"{path.name}: {error}" for error in errors)
            continue
        reports.append(report)
    return reports, problems


def md(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def fmt_fps(values: list[int]) -> str:
    if not values:
        return "n/a"
    median = statistics.median(values)
    return f"{median:g}"


def summarize_builds(builds: list[str], limit: int = 3) -> str:
    unique = sorted(set(builds))
    if len(unique) <= limit:
        return ", ".join(unique)
    return ", ".join(unique[:limit]) + f" +{len(unique) - limit}"


def cmd_validate(args) -> int:
    fork_ids = set(load_forks(args.data))
    paths = iter_report_paths(args.reports)
    error_count = 0
    for path in paths:
        try:
            report = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path.name}: {exc}", file=sys.stderr)
            error_count += 1
            continue
        errors = validate_report(path, report, fork_ids)
        for error in errors:
            print(f"{path.name}: {error}", file=sys.stderr)
        error_count += len(errors)

    print(f"{len(paths)} report(s), {error_count} error(s)")
    return 1 if error_count else 0


def cmd_render(args) -> int:
    forks = load_forks(args.data)
    reports, problems = load_reports(args.reports, set(forks))
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)

    lines = [
        "# Community reports",
        "",
        "<!-- Generated by scripts/reports.py render. Do not edit by hand. -->",
        "",
        "User-submitted experience reports, aggregated from [`data/reports/`](../data/reports/). "
        "They are anecdotes, not benchmarks. See the [reporting guide](../data/reports/README.md) "
        "and the [main fork guide](../README.md).",
        "",
    ]

    if not reports:
        lines += [
            "_No reports yet. [Open an experience report](../issues/new?template=experience-report.yml) "
            "to add the first one._",
            "",
        ]
    else:
        games = {report["game"].strip().lower() for report in reports}
        used_forks = {report["fork_id"] for report in reports}
        lines += [
            f"{len(reports)} reports, {len(games)} games, {len(used_forks)} forks",
            "",
            "## Best reported combinations",
            "",
            "| Game | Fork | Best reported | Builds | Reports | Typical FPS |",
            "|---|---|---|---|---|---|",
        ]

        groups: dict[tuple[str, str], dict] = {}
        for report in reports:
            key = (report["game"].strip().lower(), report["fork_id"])
            group = groups.setdefault(
                key,
                {"game": report["game"].strip(), "fork_id": report["fork_id"], "reports": []},
            )
            group["reports"].append(report)

        rows = []
        for group in groups.values():
            best = max(group["reports"], key=lambda r: STATUS_RANK[r["status"]])
            fps_values = [
                r["fps_typical"] for r in group["reports"] if is_int(r.get("fps_typical"))
            ]
            rows.append(
                {
                    "game": group["game"],
                    "fork_id": group["fork_id"],
                    "status": best["status"],
                    "builds": summarize_builds([r["build"] for r in group["reports"]]),
                    "count": len(group["reports"]),
                    "fps": fmt_fps(fps_values),
                    "median": statistics.median(fps_values) if fps_values else -1,
                }
            )

        rows.sort(key=lambda row: (-STATUS_RANK[row["status"]], -row["count"], -row["median"], row["game"].lower()))
        for row in rows:
            fork = forks.get(row["fork_id"], {})
            fork_name = fork.get("name", row["fork_id"])
            lines.append(
                "| {game} | {fork} | {status} | {builds} | {count} | {fps} |".format(
                    game=md(row["game"]),
                    fork=md(fork_name),
                    status=STATUS_LABEL[row["status"]],
                    builds=md(row["builds"]),
                    count=row["count"],
                    fps=row["fps"],
                )
            )

        lines += [
            "",
            "## All reports",
            "",
            "| Date | Game | Fork | Build | Platform | CPU | GPU | Status | FPS | Reporter |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for report in sorted(
            reports,
            key=lambda r: (r["date"], r["game"].lower(), r["reporter"].lower()),
            reverse=True,
        ):
            fork_name = forks.get(report["fork_id"], {}).get("name", report["fork_id"])
            reporter = report["reporter"]
            if report.get("source_url"):
                reporter = f"[{reporter}]({report['source_url']})"
            fps = report.get("fps_typical")
            fps_text = str(fps) if is_int(fps) else "n/a"
            lines.append(
                "| {date} | {game} | {fork} | {build} | {platform} | {cpu} | {gpu} | {status} | {fps} | {reporter} |".format(
                    date=report["date"],
                    game=md(report["game"]),
                    fork=md(fork_name),
                    build=md(report["build"]),
                    platform=md(report["platform"]),
                    cpu=md(report["cpu"]),
                    gpu=md(report["gpu"]),
                    status=STATUS_LABEL[report["status"]],
                    fps=fps_text,
                    reporter=md(reporter),
                )
            )

        lines += [
            "",
            f"_Latest report: {max(report['date'] for report in reports)}._",
            "",
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(reports)} report(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate every report file")
    validate.add_argument("--data", type=Path, default=ROOT / "data" / "forks.json")
    validate.add_argument("--reports", type=Path, default=ROOT / "data" / "reports")
    validate.set_defaults(func=cmd_validate)

    render = subparsers.add_parser("render", help="regenerate docs/REPORTS.md")
    render.add_argument("--data", type=Path, default=ROOT / "data" / "forks.json")
    render.add_argument("--reports", type=Path, default=ROOT / "data" / "reports")
    render.add_argument("--out", type=Path, default=ROOT / "docs" / "REPORTS.md")
    render.set_defaults(func=cmd_render)

    args = parser.parse_args()
    if not args.data.is_file():
        print(f"error: data file not found: {args.data}", file=sys.stderr)
        return 2
    if not args.reports.is_dir():
        print(f"error: reports directory not found: {args.reports}", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
