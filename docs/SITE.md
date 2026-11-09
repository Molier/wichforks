# Live status page

The guide is written by hand and carries a "last verified" date. Builds land several times a day, so the release fields go out of date within hours. The status page fills that gap: it lists every project from the data files next to what its repository reports right now.

It does not test anything and it does not rank anything. The picks and their reasoning stay in the [main guide](../README.md).

## What it shows

- A game, platform and GPU filter over the forks in [`data/forks.json`](../data/forks.json) and the native ports in [`data/ports.json`](../data/ports.json).
- For each project: the newest release and its age, downloads of that release, commits in the last 7 days, licence, what sits at the top level of the repository, and the confidence label from the data file.
- Experience reports per project and game, with a link that opens the report form with the game filled in.
- Guide maintenance: repositories that were renamed, removed or archived, and entries where the data file lists an older release than the repository has.
- Lookalike repositories from [`data/lookalikes.json`](../data/lookalikes.json), marked as possible spam.

A filter selection is kept in the address, so a link such as `#game=zelda-oot-remake&platform=linux` can be shared.

## Where the data comes from

| Data | Source | Kept in the repository |
|---|---|---|
| Roles, platforms, GPU notes, "best for", confidence, notes | `data/forks.json`, `data/ports.json` | Yes, edited by hand |
| Game names and aliases | `data/games.json` | Yes, edited by hand |
| Release, stars, pushes, commits, top-level files, renames | GitHub, Forgejo and GitLab APIs | No, read on every build |
| Reviewed reports | `data/reports/*.json` | Yes |
| Unreviewed reports and thumbs-up counts | Issues with the `experience-report` label | No, read on every build |

Nothing generated is committed, so the page adds no bot commits and no "is it current" check to CI.

A fork is shown for a game when one of its `best_for` strings contains the game's name or an alias as a whole word. A native port names its game directly.

## Enabling it

1. Merge the workflow [`.github/workflows/status-site.yml`](../.github/workflows/status-site.yml).
2. In the repository settings, open Pages and set the source to "GitHub Actions".
3. Run the "Status site" workflow once from the Actions tab, or wait for the next hour.

Until step 2 is done the workflow checks for Pages, finds none and stops without an error. After that it rebuilds every hour and on every push that touches the data or the site. GitHub pauses scheduled workflows in a repository with no activity for 60 days; running the workflow by hand starts them again.

## Running it locally

```bash
python -I scripts/site.py validate
python -I scripts/test_site.py
GITHUB_TOKEN=... python -I scripts/site.py build --out _site
python -m http.server --directory _site 8000
```

- With a token the build makes about five API calls per GitHub repository.
- Without a token it reads only the repository and its releases, to stay under GitHub's limit of 60 anonymous calls an hour. Commit counts and top-level files are then missing.
- `--offline` skips the network and builds the page from the data files alone.
- `python -I scripts/site.py status` prints the status table and the list of entries that need attention.

A lookup that fails marks that project "unknown" and the build continues.

## Reports and thumbs-up

The page counts two things per project and game:

- reports, by result (perfect, playable, broken, won't boot);
- thumbs-up reactions on a report's issue, which stand for "same result here".

Thumbs-up counts are raw GitHub reaction totals. They are not filtered by account age and they do not change any pick in the guide; the rule of two independent reports in [CONTRIBUTING.md](../CONTRIBUTING.md) still decides that.

A report filed with the issue form is read field by field. A free-text issue is listed with its title only, as "unreviewed".

## Limits

- "Top level" lists build files and counts folders at the root of the repository. It is a hint for the [source audit](SOURCE-AUDIT.md), not a replacement: a repository can pass it and still not build.
- The newest release is the one with the latest publish date, pre-releases included. When that is a pre-release, the newest full release is shown as well.
- Download counts cover release assets only. Projects that publish through Actions artifacts or other hosts show lower numbers.
- Forgejo and GitLab projects get release and repository data, but no commit counts.
