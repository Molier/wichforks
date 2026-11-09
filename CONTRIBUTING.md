# Contributing

Thanks for helping keep this list useful. The Switch 2 emulation scene changes hourly, so the main job is accurate, dated, source-linked updates.

## Rules

1. One fork per PR. Don't bundle unrelated additions.
2. Link upstream. Every entry needs the repository URL (GitHub or Forgejo) and, when available, the releases page.
3. State the evidence. For each game claim, say whether it comes from:
   - the fork's README or release notes (documented), or
   - a community report (community-reported), with a link and date.
4. Include context: platform, GPU and driver, build tag, and game tested.
5. No copyrighted files. No ROMs, keys, firmware or links to them. No "repack" or ad-gated download links.
6. Update, don't duplicate. If a fork already has a row, edit the row and bump its release or build fields.
7. First picks must publish full source in the repo under a license. A source zip in a release or a binary-only fork is not enough: mark it unverified and keep it out of the first-pick rows.

## Reporting your experience

You don't need to write JSON to contribute a data point.

- Fast path: open an [experience report](issues/new?template=experience-report.yml) issue. Use the exact build tag, game title, CPU, GPU and driver, RAM, settings and outcome.
- From a public thread: run [the single-thread intake script](docs/INTAKE.md) on one URL, review the candidates in `data/reports/inbox/`, then move the edited file to `data/reports/`. The script does not crawl subreddits.
- Structured path: add `data/reports/YYYY-MM-DD-<fork-id>-<slug>.json` following [data/reports/README.md](data/reports/README.md), then run:

```bash
python -I scripts/reports.py validate
python -I scripts/reports.py render
```

Rules:

- One report per build, game and config. Duplicates from the same reporter are collapsed.
- No ROMs, keys, firmware or links to them.
- Reports are public; use your GitHub handle.
- Don't edit someone else's report. Add a new one or open an issue with a correction.
- A recommendation changes only after two independent reports on the same game, fork and GPU class agree.

Maintainers: create the `experience-report` label if it doesn't exist, and regenerate `docs/REPORTS.md` after merging reports.

## Adding a fork

Add an entry to `data/forks.json`:

```json
{
  "id": "short-slug",
  "name": "Display Name (Author)",
  "repo": "https://github.com/author/repo",
  "releases": "https://github.com/author/repo/releases",
  "host": "GitHub",
  "role": "one-line role",
  "platforms": ["Windows"],
  "gpu": ["NVIDIA", "AMD"],
  "best_for": ["Game or use case"],
  "latest_release": { "tag": "build-1", "date": "2026-11-05", "prerelease": true },
  "license": "GPL-3.0",
  "stars_at_check": 0,
  "confidence": "documented",
  "notes": "Short, factual, sourced."
}
```

Allowed `confidence` values: `documented`, `community-reported`, `source-only`, `unverified`.

Then add the fork to the relevant README tables and, if necessary, the game matrix. Use the same wording as the JSON so the two don't drift.

## Adding a native port

Static recompilations and other native builds of a single game are not forks, so they go in `data/ports.json`:

```json
{
  "id": "short-slug",
  "name": "Display Name (Author)",
  "game": "id from data/games.json",
  "kind": "static recompilation",
  "state": "experimental",
  "repo": "https://github.com/author/repo",
  "releases": "https://github.com/author/repo/releases",
  "host": "GitHub",
  "platforms": ["Windows 10/11 x64"],
  "gpu": ["Vulkan 1.3"],
  "game_version": "1.0.0",
  "license": "GPL-3.0",
  "source_in_repo": true,
  "confidence": "documented",
  "checked": "2026-11-10",
  "notes": "Short, factual, sourced."
}
```

- Allowed `state` values: `playable`, `experimental`, `not playable`, `superseded`. Use the project's own README wording; do not upgrade it.
- `checked` is the day you read the README or release notes.
- Leave out release tags, stars and dates. The [status page](docs/SITE.md) reads them from the repository.
- The same rules apply as for forks: one port per PR, source in the repository, no game files, keys or links to them.

A new game needs an entry in `data/games.json` with an `id`, a `name` and the `aliases` people use for it in `best_for` strings. Titles only, no title IDs.

## Lookalike repositories

`data/lookalikes.json` lists repositories that reuse the name of a listed project without being that project. The status page shows them as possible spam. A row states only what the repository itself shows (not a fork of upstream, no source tree, binary-only release) and the day it was checked. Do not write "malware" unless the upstream project says so in its own README or issue tracker, and link that. Remove the row when the repository is gone.

## Checking links and reports

```bash
python -I scripts/check_links.py
python -I scripts/reports.py validate
python -I scripts/performance_data.py
python -I scripts/site.py validate
python -I scripts/test_site.py
```

The link checker exits non-zero on dead (404/410) or unreachable URLs. Rate limits and 5xx answers are retried, then reported as INCONCLUSIVE without failing the run. The report validator exits non-zero on schema errors. After editing a performance table, regenerate the JSON, SVG charts and coverage page, and commit them; CI checks that they are current. Fix dead links or mark the fork as archived or removed in the same PR.

## Removing a fork

Forks disappear (DMCA, renames, abandoned accounts). If a link is dead:

- Try to find the renamed repo first.
- If it's gone, remove it from the tables and note the removal in the update log.
- Don't silently replace a dead link with a random mirror.

## Style

- English, short sentences, no hype.
- Use "community-reported" instead of presenting unverified FPS numbers as fact.
- Prefer recent reports. A 31 Oct report on an old build is history, not evidence for the current build.
- A self-reported release note from a release-only repo needs independent confirmation before it changes a first pick.
- Keep the confidence labels and the `Last verified` date honest.

## Update log

Add a row to the README update log with the date and a one-line summary.
