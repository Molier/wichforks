#!/usr/bin/env python3
"""Validate the site data, read live project status and build the status site.

Usage:
    python -I scripts/site.py validate
    python -I scripts/site.py status
    python -I scripts/site.py build --out _site
    python -I scripts/site.py build --out _site --offline

`validate` checks data/games.json, data/ports.json and data/lookalikes.json.
`status` prints what the host APIs say about every listed repository.
`build` writes a static site: the files in site/ plus one data.json that holds
the curated data, the live status and the experience reports.

Set GITHUB_TOKEN (or GH_TOKEN) for the full status. Without a token the script
stays under GitHub's anonymous limit by reading the repository and its releases
only. A failed lookup never fails the build: that project is marked "unknown".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "whichforks-site/1.0"
DEFAULT_REPO = "riyadhHDA/wichforks"
CONFIDENCE = {"documented", "community-reported", "source-only", "unverified"}
PORT_STATES = {"playable", "experimental", "not playable", "superseded"}
PORT_REQUIRED = ("id", "name", "game", "kind", "state", "repo", "host", "platforms", "license", "confidence", "checked", "notes")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
BUILD_FILES = {
    "CMakeLists.txt", "Makefile", "meson.build", "Cargo.toml", "build.gradle",
    "build.gradle.kts", "package.json", "pyproject.toml", "setup.py", "build.zig",
}
NON_CODE_DIRS = {".github", ".vscode", "docs", "doc", "image", "images", "assets", "screenshots", "media"}
STATUS_KEYS = (("perfect", "perfect"), ("playable", "playable"), ("broken", "broken"), ("won't boot", "wont-boot"), ("wont-boot", "wont-boot"))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_data(root: Path) -> dict:
    data = {
        "forks": load_json(root / "data" / "forks.json").get("forks", []),
        "ports": [],
        "games": [],
        "lookalikes": [],
    }
    for key, name in (("ports", "ports.json"), ("games", "games.json"), ("lookalikes", "lookalikes.json")):
        path = root / "data" / name
        if path.exists():
            data[key] = load_json(path).get(key, [])
    return data


# ---------------------------------------------------------------- validation


def is_https(value) -> bool:
    return isinstance(value, str) and value.startswith("https://") and " " not in value


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    fork_ids = {fork.get("id") for fork in data["forks"]}

    game_ids: set[str] = set()
    for index, game in enumerate(data["games"]):
        where = f"games.json[{index}]"
        gid = game.get("id")
        if not isinstance(gid, str) or not ID_RE.match(gid):
            errors.append(f"{where}: id must be a lowercase slug")
            continue
        if gid in game_ids:
            errors.append(f"{where}: duplicate id {gid}")
        game_ids.add(gid)
        if not isinstance(game.get("name"), str) or not game["name"].strip():
            errors.append(f"{where}: name is required")
        aliases = game.get("aliases")
        if not isinstance(aliases, list) or not aliases or not all(isinstance(a, str) and a.strip() for a in aliases):
            errors.append(f"{where}: aliases must be a non-empty list of strings")
        guide = game.get("guide")
        if guide is not None and not (ROOT / guide).exists():
            errors.append(f"{where}: guide {guide} does not exist")

    port_ids: set[str] = set()
    for index, port in enumerate(data["ports"]):
        where = f"ports.json[{index}] ({port.get('id', '?')})"
        for field in PORT_REQUIRED:
            if field not in port:
                errors.append(f"{where}: missing {field}")
        pid = port.get("id")
        if not isinstance(pid, str) or not ID_RE.match(pid):
            errors.append(f"{where}: id must be a lowercase slug")
        elif pid in port_ids or pid in fork_ids:
            errors.append(f"{where}: id {pid} is already used")
        port_ids.add(pid)
        if port.get("game") not in game_ids:
            errors.append(f"{where}: game {port.get('game')!r} is not in games.json")
        if port.get("confidence") not in CONFIDENCE:
            errors.append(f"{where}: confidence must be one of {sorted(CONFIDENCE)}")
        if port.get("state") not in PORT_STATES:
            errors.append(f"{where}: state must be one of {sorted(PORT_STATES)}")
        if not is_https(port.get("repo")):
            errors.append(f"{where}: repo must be an https URL")
        if port.get("releases") is not None and not is_https(port.get("releases")):
            errors.append(f"{where}: releases must be an https URL")
        if not isinstance(port.get("platforms"), list) or not port.get("platforms"):
            errors.append(f"{where}: platforms must be a non-empty list")
        if not DATE_RE.match(str(port.get("checked", ""))):
            errors.append(f"{where}: checked must be YYYY-MM-DD")

    known = fork_ids | port_ids
    for index, row in enumerate(data["lookalikes"]):
        where = f"lookalikes.json[{index}]"
        if not is_https(row.get("repo")):
            errors.append(f"{where}: repo must be an https URL")
        if row.get("imitates") not in known:
            errors.append(f"{where}: imitates {row.get('imitates')!r} is not a listed project")
        if not isinstance(row.get("facts"), str) or not row["facts"].strip():
            errors.append(f"{where}: facts is required")
        if not DATE_RE.match(str(row.get("checked", ""))):
            errors.append(f"{where}: checked must be YYYY-MM-DD")
    return errors


# ------------------------------------------------------------------ HTTP


class Api:
    """Small JSON client that remembers GitHub's rate limit."""

    def __init__(self, token: str | None, timeout: int = 20):
        self.token = token
        self.timeout = timeout
        self.calls = 0
        self.rate_limited = False

    def get(self, url: str, github: bool = True):
        """Return (status, parsed JSON or None, headers)."""
        if github and self.rate_limited:
            return 429, None, {}
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if github:
            headers["Accept"] = "application/vnd.github+json"
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        self.calls += 1
        try:
            with urlopen(Request(url, headers=headers), timeout=self.timeout) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None, dict(response.headers)
        except HTTPError as exc:
            if github and exc.code in (403, 429) and exc.headers.get("X-RateLimit-Remaining") == "0":
                self.rate_limited = True
                return 429, None, dict(exc.headers)
            return exc.code, None, dict(exc.headers)
        except (URLError, OSError, json.JSONDecodeError):
            return None, None, {}


def last_page(headers: dict, fallback: int) -> int:
    match = re.search(r'[?&]page=(\d+)>; rel="last"', headers.get("Link", "") or headers.get("link", ""))
    return int(match.group(1)) if match else fallback


def release_summary(releases: list, tag_key: str, date_key: str, url_key: str | None) -> dict | None:
    dated = [r for r in releases if r.get(date_key)]
    if not dated:
        return None
    newest = max(dated, key=lambda r: r[date_key])
    assets = newest.get("assets") or []
    if isinstance(assets, dict):  # GitLab: {"links": [...], "sources": [...]}
        assets = assets.get("links") or []
    return {
        "tag": newest.get(tag_key),
        "date": newest[date_key],
        "prerelease": bool(newest.get("prerelease")),
        "url": newest.get(url_key) if url_key else None,
        "assets": [a.get("name") for a in assets if a.get("name")][:12],
        "downloads": sum(a.get("download_count") or 0 for a in assets),
    }


def github_status(api: Api, owner: str, repo: str, full: bool) -> dict:
    listed = f"{owner}/{repo}"
    status, body, _ = api.get(f"https://api.github.com/repos/{owner}/{repo}")
    if status == 404:
        return {"host": "GitHub", "state": "gone", "listed": listed}
    if status != 200 or not body:
        return {"host": "GitHub", "state": "unknown", "listed": listed, "error": f"HTTP {status}"}

    name = body["full_name"]
    out = {
        "host": "GitHub",
        "state": "archived" if body.get("archived") else "renamed" if name.lower() != listed.lower() else "ok",
        "listed": listed,
        "full_name": name,
        "html_url": body["html_url"],
        "stars": body.get("stargazers_count"),
        "forks": body.get("forks_count"),
        "license": (body.get("license") or {}).get("spdx_id"),
        "created_at": body.get("created_at"),
        "pushed_at": body.get("pushed_at"),
        "is_fork": bool(body.get("fork")),
        "parent": (body.get("parent") or {}).get("full_name"),
    }
    base = f"https://api.github.com/repos/{name}"

    status, releases, _ = api.get(f"{base}/releases?per_page=30")
    if status == 200 and isinstance(releases, list):
        out["release"] = release_summary(releases, "tag_name", "published_at", "html_url")
        if out["release"] and out["release"]["prerelease"]:
            stable = release_summary([r for r in releases if not r.get("prerelease")], "tag_name", "published_at", "html_url")
            if stable:
                out["stable_release"] = {"tag": stable["tag"], "date": stable["date"], "url": stable["url"]}
        out["releases_seen"] = len(releases)
        out["downloads_seen"] = sum(a.get("download_count") or 0 for r in releases for a in r.get("assets") or [])
    if not full:
        return out

    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    status, commits, headers = api.get(f"{base}/commits?per_page=1&since={since}")
    if status == 200 and isinstance(commits, list):
        out["commits_7d"] = last_page(headers, len(commits))
    status, commits, headers = api.get(f"{base}/commits?per_page=1")
    if status == 200 and isinstance(commits, list):
        out["commits_total"] = last_page(headers, len(commits))
    status, entries, _ = api.get(f"{base}/contents/")
    if status == 200 and isinstance(entries, list):
        names = [e["name"] for e in entries]
        dirs = [e["name"] for e in entries if e.get("type") == "dir" and e["name"].lower() not in NON_CODE_DIRS]
        out["tree"] = {
            "license_file": any(n.upper().startswith(("LICENSE", "LICENCE", "COPYING")) for n in names),
            "build_files": sorted(n for n in names if n in BUILD_FILES or n.endswith(".sln")),
            "code_dirs": len(dirs),
            "entries": len(names),
        }
    return out


def forgejo_status(api: Api, url: str) -> dict:
    parsed = urlparse(url)
    owner, repo = parsed.path.strip("/").split("/")[:2]
    base = f"{parsed.scheme}://{parsed.netloc}/api/v1/repos/{owner}/{repo}"
    status, body, _ = api.get(base, github=False)
    if status == 404:
        return {"host": "Forgejo", "state": "gone", "listed": f"{owner}/{repo}"}
    if status != 200 or not body:
        return {"host": "Forgejo", "state": "unknown", "listed": f"{owner}/{repo}", "error": f"HTTP {status}"}
    out = {
        "host": "Forgejo",
        "state": "archived" if body.get("archived") else "ok",
        "listed": f"{owner}/{repo}",
        "full_name": body.get("full_name"),
        "html_url": body.get("html_url"),
        "stars": body.get("stars_count"),
        "forks": body.get("forks_count"),
        "created_at": body.get("created_at"),
        "pushed_at": body.get("updated_at"),
        "is_fork": bool(body.get("fork")),
    }
    status, releases, _ = api.get(f"{base}/releases?limit=10", github=False)
    if status == 200 and isinstance(releases, list):
        out["release"] = release_summary(releases, "tag_name", "published_at", "html_url")
    return out


def gitlab_status(api: Api, url: str) -> dict:
    path = urlparse(url).path.strip("/")
    base = f"https://gitlab.com/api/v4/projects/{quote(path, safe='')}"
    status, body, _ = api.get(base, github=False)
    if status == 404:
        return {"host": "GitLab", "state": "gone", "listed": path}
    if status != 200 or not body:
        return {"host": "GitLab", "state": "unknown", "listed": path, "error": f"HTTP {status}"}
    out = {
        "host": "GitLab",
        "state": "archived" if body.get("archived") else "ok",
        "listed": path,
        "full_name": body.get("path_with_namespace"),
        "html_url": body.get("web_url"),
        "stars": body.get("star_count"),
        "forks": body.get("forks_count"),
        "created_at": body.get("created_at"),
        "pushed_at": body.get("last_activity_at"),
    }
    status, releases, _ = api.get(f"{base}/releases?per_page=10", github=False)
    if status == 200 and isinstance(releases, list):
        out["release"] = release_summary(releases, "tag_name", "released_at", None)
    return out


def project_status(api: Api, url: str, full: bool) -> dict:
    parsed = urlparse(url or "")
    parts = parsed.path.strip("/").split("/")
    try:
        if parsed.netloc == "github.com" and len(parts) >= 2:
            return github_status(api, parts[0], parts[1], full)
        if parsed.netloc == "gitlab.com" and len(parts) >= 2:
            return gitlab_status(api, url)
        if len(parts) >= 2:
            return forgejo_status(api, url)
    except (KeyError, ValueError, TypeError) as exc:
        return {"state": "unknown", "error": f"unexpected answer: {exc}"}
    return {"state": "unknown", "error": "unsupported URL"}


def collect_status(data: dict, api: Api, delay: float = 0.0) -> dict:
    full = bool(api.token)
    out: dict[str, dict] = {}
    for project in data["forks"] + data["ports"]:
        out[project["id"]] = project_status(api, project.get("repo"), full)
        time.sleep(delay)
    for row in data["lookalikes"]:
        out["lookalike:" + row["repo"]] = project_status(api, row["repo"], False)
        time.sleep(delay)
    return out


# ---------------------------------------------------------------- reports


def form_labels(root: Path) -> dict[str, str]:
    """Map each label of the experience report form to its field id."""
    path = root / ".github" / "ISSUE_TEMPLATE" / "experience-report.yml"
    labels: dict[str, str] = {}
    if not path.exists():
        return labels
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            current = stripped[3:].strip().strip("\"'")
        elif stripped.startswith("label:") and current:
            labels[stripped[6:].strip().strip("\"'").lower()] = current
            current = None
    return labels


def parse_form(body: str, labels: dict[str, str]) -> dict[str, str]:
    """Read the '### Label' sections GitHub writes for an issue form."""
    fields: dict[str, str] = {}
    sections = re.split(r"(?m)^###\s+(.+?)\s*$", body or "")
    for label, value in zip(sections[1::2], sections[2::2]):
        field = labels.get(label.strip().lower())
        value = value.strip()
        if field and value and value != "_No response_":
            fields[field] = value
    return fields


def word_in(needle: str, haystack: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(needle.lower()) + r"(?![a-z0-9])", haystack.lower()) is not None


def match_game(text: str, games: list) -> str | None:
    for game in games:
        if any(word_in(alias, text) for alias in [game["name"], *game.get("aliases", [])]):
            return game["id"]
    return None


def match_project(text: str, projects: list) -> str | None:
    lowered = text.lower()
    for project in projects:
        slug = urlparse(project.get("repo") or "").path.strip("/").lower()
        if slug and slug in lowered:
            return project["id"]
    for project in projects:
        short = re.sub(r"\s*\(.*\)$", "", project.get("name", "")).strip()
        if len(short) >= 4 and word_in(short, lowered):
            return project["id"]
    return None


def status_key(text: str) -> str | None:
    lowered = (text or "").lower()
    for prefix, key in STATUS_KEYS:
        if lowered.startswith(prefix):
            return key
    return None


def reviewed_reports(root: Path, data: dict) -> list[dict]:
    reports = []
    for path in sorted((root / "data" / "reports").glob("*.json")):
        try:
            report = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        reports.append({
            "reviewed": True,
            "project": report.get("fork_id"),
            "game": match_game(report.get("game", ""), data["games"]),
            "game_name": report.get("game"),
            "status": report.get("status"),
            "build": report.get("build"),
            "date": report.get("date"),
            "platform": report.get("platform"),
            "cpu": report.get("cpu"),
            "gpu": report.get("gpu"),
            "fps": report.get("fps_typical"),
            "reporter": report.get("reporter"),
            "url": report.get("source_url"),
            "thumbs": 0,
        })
    return reports


def issue_reports(api: Api, repo: str, root: Path, data: dict) -> list[dict]:
    labels = form_labels(root)
    projects = data["forks"] + data["ports"]
    reports = []
    for page in range(1, 6):
        status, issues, _ = api.get(f"https://api.github.com/repos/{repo}/issues?labels=experience-report&state=all&per_page=100&page={page}")
        if status != 200 or not isinstance(issues, list):
            break
        for issue in issues:
            if "pull_request" in issue:
                continue
            fields = parse_form(issue.get("body") or "", labels)
            title = issue.get("title") or ""
            reports.append({
                "reviewed": False,
                "parsed": bool(fields),
                "project": match_project(fields.get("fork") or title, projects),
                "game": match_game(fields.get("game") or title, data["games"]),
                "game_name": fields.get("game") or title.replace("[Report]", "").strip(),
                "status": status_key(fields.get("status", "")),
                "build": fields.get("build"),
                "date": (issue.get("created_at") or "")[:10],
                "platform": fields.get("platform"),
                "cpu": fields.get("cpu"),
                "gpu": fields.get("gpu"),
                "fps": fields.get("fps"),
                "reporter": (issue.get("user") or {}).get("login"),
                "url": issue.get("html_url"),
                "thumbs": (issue.get("reactions") or {}).get("+1", 0),
            })
        if len(issues) < 100:
            break
    return reports


def merge_reports(reviewed: list[dict], live: list[dict]) -> list[dict]:
    """Prefer the reviewed JSON file; keep the issue's thumbs-up count."""
    by_url = {r["url"]: r for r in live if r.get("url")}
    merged = []
    for report in reviewed:
        issue = by_url.pop(report.get("url"), None)
        if issue:
            report["thumbs"] = issue["thumbs"]
        merged.append(report)
    return merged + list(by_url.values())


# ------------------------------------------------------------------ build


def build(args) -> int:
    data = load_data(ROOT)
    errors = validate(data)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    token = None if args.offline else os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    api = Api(token)
    reviewed = reviewed_reports(ROOT, data)
    if args.offline:
        status, reports = {}, reviewed
    else:
        status = collect_status(data, api)
        reports = merge_reports(reviewed, issue_reports(api, args.repo, ROOT, data))

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "site", out)
    bundle = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": args.repo,
        "status_mode": "offline" if args.offline else "full" if token else "light",
        "rate_limited": api.rate_limited,
        **data,
        "status": status,
        "reports": reports,
    }
    (out / "data.json").write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    known = sum(1 for s in status.values() if s.get("state") not in (None, "unknown"))
    print(f"wrote {out}/ ({len(data['forks'])} forks, {len(data['ports'])} ports, {len(data['games'])} games, "
          f"{known}/{len(status)} status lookups, {len(reports)} reports, {api.calls} API calls, mode {bundle['status_mode']})")
    if api.rate_limited:
        print("warning: GitHub rate limit reached; some projects are marked unknown", file=sys.stderr)
    return 0


def print_status(args) -> int:
    data = load_data(ROOT)
    api = Api(os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    status = collect_status(data, api)
    names = {p["id"]: p["name"] for p in data["forks"] + data["ports"]}
    for key, entry in status.items():
        release = entry.get("release") or {}
        extra = f" -> {entry['full_name']}" if entry.get("state") == "renamed" else ""
        print(f"{entry.get('state', '?'):<9} {names.get(key, key):<44} {release.get('tag') or '-':<28} {(release.get('date') or '')[:10]}{extra}")
    drift = [key for key, entry in status.items() if entry.get("state") in ("gone", "renamed", "archived") and not key.startswith("lookalike:")]
    print(f"\n{len(status)} repositories, {api.calls} API calls, {len(drift)} need attention: {', '.join(drift) or 'none'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="check games.json, ports.json and lookalikes.json")
    sub.add_parser("status", help="print the live status of every listed repository")
    build_parser = sub.add_parser("build", help="write the static site")
    build_parser.add_argument("--out", default="_site")
    build_parser.add_argument("--repo", default=DEFAULT_REPO,
                              help="repository whose experience report issues are read and linked")
    build_parser.add_argument("--offline", action="store_true", help="skip every network call")
    args = parser.parse_args()

    if args.command == "validate":
        data = load_data(ROOT)
        errors = validate(data)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"ok: {len(data['games'])} games, {len(data['ports'])} ports, {len(data['lookalikes'])} lookalikes")
        return 0
    if args.command == "status":
        return print_status(args)
    return build(args)


if __name__ == "__main__":
    raise SystemExit(main())
