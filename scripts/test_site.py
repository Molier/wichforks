#!/usr/bin/env python3
"""Offline checks for scripts/site.py.

Usage:
    python -I scripts/test_site.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("site_tool", ROOT / "scripts" / "site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)

FORM_BODY = """### Fork

zortos293/Lichii

### Build / release tag

build-130

### Game

Zelda: Ocarina of Time remake

### Game version (optional)

_No response_

### Platform

Windows 11

### GPU

RTX 3060

### Status

Playable: works with glitches or drops
"""


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = site.load_data(ROOT)
        cls.projects = cls.data["forks"] + cls.data["ports"]

    def test_repository_data_is_valid(self):
        self.assertEqual(site.validate(self.data), [])

    def test_validation_reports_bad_port(self):
        broken = {**self.data, "ports": [{"id": "Bad Id", "game": "no-such-game", "repo": "http://x"}]}
        errors = "\n".join(site.validate(broken))
        for expected in ("lowercase slug", "not in games.json", "https URL", "missing name"):
            self.assertIn(expected, errors)

    def test_port_id_may_not_reuse_a_fork_id(self):
        port = {**self.data["ports"][0], "id": self.data["forks"][0]["id"]}
        self.assertIn("already used", "\n".join(site.validate({**self.data, "ports": [port]})))

    def test_issue_form_is_parsed(self):
        fields = site.parse_form(FORM_BODY, site.form_labels(ROOT))
        self.assertEqual(fields["fork"], "zortos293/Lichii")
        self.assertEqual(fields["build"], "build-130")
        self.assertNotIn("game_version", fields)
        self.assertEqual(site.status_key(fields["status"]), "playable")
        self.assertEqual(site.match_project(fields["fork"], self.projects), "lichii")
        self.assertEqual(site.match_game(fields["game"], self.data["games"]), "zelda-oot-remake")

    def test_free_text_issue_has_no_fields(self):
        self.assertEqual(site.parse_form("- Game: Mario Kart World\n- GPU: RTX 3090", site.form_labels(ROOT)), {})

    def test_every_form_fork_option_resolves(self):
        template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "experience-report.yml").read_text(encoding="utf-8")
        options = [line.strip()[3:-1] for line in template.splitlines() if line.strip().startswith('- "') and "/" in line]
        self.assertTrue(options)
        for option in options:
            if option.startswith("Other"):
                continue
            self.assertIsNotNone(site.match_project(option, self.projects), option)

    def test_game_aliases_match_whole_words_only(self):
        games = self.data["games"]
        self.assertEqual(site.match_game("Zelda OoT remake (build-88+)", games), "zelda-oot-remake")
        self.assertEqual(site.match_game("Hyrule Warriors (build 202+)", games), "hyrule-warriors-aoi")
        self.assertIsNone(site.match_game("reboot the emulator smoothly", games))
        self.assertIsNone(site.match_game("first install", games))

    def test_release_summary_picks_newest(self):
        releases = [
            {"tag_name": "a", "published_at": "2026-11-01T00:00:00Z", "prerelease": False, "assets": []},
            {"tag_name": "b", "published_at": "2026-11-03T00:00:00Z", "prerelease": True,
             "assets": [{"name": "x.zip", "download_count": 5}, {"name": "y.zip", "download_count": 7}]},
            {"tag_name": "draft", "published_at": None},
        ]
        summary = site.release_summary(releases, "tag_name", "published_at", None)
        self.assertEqual((summary["tag"], summary["downloads"], summary["prerelease"]), ("b", 12, True))
        self.assertIsNone(site.release_summary([], "tag_name", "published_at", None))

    def test_reviewed_report_keeps_issue_thumbs(self):
        reviewed = [{"url": "https://example.invalid/1", "thumbs": 0, "reviewed": True}]
        live = [{"url": "https://example.invalid/1", "thumbs": 4, "reviewed": False},
                {"url": "https://example.invalid/2", "thumbs": 1, "reviewed": False}]
        merged = site.merge_reports(reviewed, live)
        self.assertEqual([(r["url"][-1], r["thumbs"], r["reviewed"]) for r in merged], [("1", 4, True), ("2", 1, False)])

    def test_last_page_reads_link_header(self):
        header = {"Link": '<https://api.github.com/x?per_page=1&page=2>; rel="next", <https://api.github.com/x?per_page=1&page=627>; rel="last"'}
        self.assertEqual(site.last_page(header, 1), 627)
        self.assertEqual(site.last_page({}, 1), 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
