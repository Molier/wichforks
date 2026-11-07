#!/usr/bin/env python3
"""Scrape the public Lichii compatibility reports.

Usage:
    python -I scripts/scrape_lichii.py
    python -I scripts/scrape_lichii.py --delay 1.0
    python -I scripts/scrape_lichii.py --limit 20

Reads the public sitemap, fetches /reports/<id> pages only, and writes
data/lichii-reports.json. It does not call /api/v1/, /submit or any
authenticated endpoint. Raw HTML is cached outside the repository.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SITEMAP_URL = "https://lichii.zortos.me/sitemap.xml"
USER_AGENT = "whichforks-research/1.0 (+https://github.com/riyadhHDA/wichforks)"
CACHE = Path.home() / ".cache" / "whichforks" / "lichii-reports"
OUT = ROOT / "data" / "lichii-reports.json"

SECTION_RE = re.compile(
    r"<section><h2>(.*?)</h2><p class=\"preserve-lines\">(.*?)</p></section>",
    re.S,
)
FACT_RE = re.compile(r"<div><dt>(.*?)</dt><dd>(.*?)</dd></div>", re.S)
STATUS_RE = re.compile(r"<span class=\"status status-[^\"]*\"><i[^>]*></i>(.*?)</span>", re.S)
GAME_RE = re.compile(r"<span class=\"status[^\"]*\">.*?</span>\s*<a href=\"/games/[^\"]+\">(.*?)</a>", re.S)
TIME_RE = re.compile(r"<time datetime=\"([^\"]+)\">(.*?)</time>", re.S)
TITLE_RE = re.compile(r"<h1 class=\"page-title\">(.*?)</h1>", re.S)


def clean_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    lines = [line.strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_fps(text: str) -> tuple[int | None, int | None]:
    values: list[int] = []
    for low, high in re.findall(r"(\d{2,3})\s*(?:-|to|/)\s*(\d{2,3})\s*fps", text, re.I):
        values.extend([int(low), int(high)])
    for value in re.findall(r"(?<![\d-])(\d{2,3})\s*fps", text, re.I):
        values.append(int(value))
    if not values:
        return None, None
    return min(values), max(values)


def ram_gb(value: str) -> int | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:GB|GiB|GM)", value, re.I)
    return round(float(match.group(1))) if match else None


def gpu_vendor(value: str) -> str:
    text = value.lower()
    if any(token in text for token in ("rtx", "gtx", "nvidia", "quadro")):
        return "NVIDIA"
    if any(token in text for token in ("rx ", "radeon", "amd")):
        return "AMD"
    if any(token in text for token in ("intel", "arc", "iris")):
        return "Intel"
    if "apple" in text or re.search(r"\bm[1-5]\b", text):
        return "Apple"
    return "Unknown"


def os_family(value: str) -> str:
    text = value.lower()
    if "windows" in text:
        return "Windows"
    if any(token in text for token in ("linux", "cachyos", "arch", "ubuntu", "fedora", "nobara")):
        return "Linux"
    if any(token in text for token in ("macos", "mac os", "osx")):
        return "macOS"
    return "Unknown"


def build_family(value: str) -> str:
    match = re.search(r"build[- ]?(\d{2,3})", value, re.I)
    if match:
        return f"build-{match.group(1)}"
    stripped = value.strip()
    if re.fullmatch(r"\d{2,3}", stripped):
        return f"build-{stripped}"
    if "frizti" in value.lower():
        return "Frizti"
    return value


def fetch(url: str, timeout: int) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def sitemap_urls() -> list[str]:
    cache_path = CACHE / "sitemap.xml"
    CACHE.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        xml = cache_path.read_text(encoding="utf-8")
    else:
        xml = fetch(SITEMAP_URL, 30)
        cache_path.write_text(xml, encoding="utf-8")
    urls = re.findall(r"<loc>(https://lichii\.zortos\.me/reports/[^<]+)</loc>", xml)
    return sorted(set(urls))


def parse_report(url: str, source: str) -> dict | None:
    status_match = STATUS_RE.search(source)
    game_match = GAME_RE.search(source)
    time_match = TIME_RE.search(source)
    title_match = TITLE_RE.search(source)
    if not (status_match and game_match and time_match):
        return None

    sections = {}
    for heading, body in SECTION_RE.findall(source):
        sections[clean_text(heading).lower()] = clean_text(body)

    facts = {}
    for label, value in FACT_RE.findall(source):
        facts[clean_text(label).lower()] = clean_text(value)

    reported_at = time_match.group(1)
    try:
        date_label = datetime.fromisoformat(reported_at.replace("Z", "+00:00")).astimezone(timezone.utc).date().isoformat()
    except ValueError:
        date_label = time_match.group(2)[:10]

    report_id = url.rstrip("/").rsplit("/", 1)[-1]
    what_happened = sections.get("what happened", "")
    title = clean_text(title_match.group(1)) if title_match else ""
    how_far = sections.get("how far they got", "")
    fps_min, fps_max = parse_fps("\n".join([what_happened, title, how_far]))
    build = facts.get("lichii build", "")
    gpu = facts.get("gpu", "")
    os_name = facts.get("operating system", "")
    return {
        "id": report_id,
        "url": url,
        "date": date_label,
        "reported_at": reported_at,
        "game": clean_text(game_match.group(1)),
        "status": clean_text(status_match.group(1)),
        "title": title,
        "what_happened": what_happened,
        "how_far": how_far,
        "steps": sections.get("steps to reproduce", ""),
        "settings": sections.get("settings", ""),
        "build": build,
        "build_family": build_family(build),
        "build_section": facts.get("build section", ""),
        "game_version": facts.get("game version", ""),
        "cpu": facts.get("cpu", ""),
        "gpu": gpu,
        "gpu_vendor": gpu_vendor(gpu),
        "gpu_driver": facts.get("gpu driver", ""),
        "os": os_name,
        "os_family": os_family(os_name),
        "ram": facts.get("ram", ""),
        "ram_gb": ram_gb(facts.get("ram", "")),
        "graphics_api": facts.get("graphics api", ""),
        "fps_min": fps_min,
        "fps_max": fps_max,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    parser.add_argument("--limit", type=int, default=0, help="only fetch the first N reports")
    parser.add_argument("--timeout", type=int, default=25)
    args = parser.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    urls = sitemap_urls()
    if args.limit:
        urls = urls[: args.limit]
    print(f"{len(urls)} report pages")

    reports = []
    errors = []
    for index, url in enumerate(urls, 1):
        report_id = url.rstrip("/").rsplit("/", 1)[-1]
        cache_path = CACHE / f"{report_id}.html"
        try:
            if cache_path.exists():
                source = cache_path.read_text(encoding="utf-8")
            else:
                source = fetch(url, args.timeout)
                cache_path.write_text(source, encoding="utf-8")
                time.sleep(max(0.0, args.delay))
            parsed = parse_report(url, source)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            errors.append({"url": url, "error": str(exc)})
            print(f"  {index}/{len(urls)} ERROR {report_id}: {exc}", file=sys.stderr)
            continue
        if parsed:
            reports.append(parsed)
            print(f"  {index}/{len(urls)} {parsed['date']} {parsed['game']} ({parsed['status']})")
        else:
            errors.append({"url": url, "error": "could not parse report page"})
            print(f"  {index}/{len(urls)} PARSE FAIL {report_id}", file=sys.stderr)

    reports.sort(key=lambda row: (row["reported_at"], row["game"]), reverse=True)
    data = {
        "scraped": datetime.now(timezone.utc).date().isoformat(),
        "source": "https://lichii.zortos.me/reports",
        "note": "Public Lichii compatibility reports. No usernames are collected. See each report URL for the original.",
        "count": len(reports),
        "errors": errors,
        "reports": reports,
    }
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {len(reports)} reports to {OUT} ({len(errors)} errors)")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
