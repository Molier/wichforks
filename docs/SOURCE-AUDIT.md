# Source audit

Checked 7 Nov 2026 against the GitHub, Forgejo and GitLab APIs. A project is auditable when the full source is in the repository, a license file is present, and the build files are there. A source zip attached to a release is not the same as a public source tree.

| Project | License | Full source in repo | Release assets | History | Status |
|---|---|---|---|---|---|
| [Djihads80/Eglantine](https://github.com/Djihads80/Eglantine) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Large | Auditable |
| [EddizEge/Anka](https://github.com/EddizEge/Anka) | GPL-3.0 | Yes, src and CMakeLists | Windows zip, PDB, three source zips, SHA256SUMS | New, one release | Auditable source; new project, self-reported DK result |
| [SmileyTatsu/Eglantine](https://github.com/SmileyTatsu/Eglantine) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Active fork | Auditable |
| [MythosOfs/Orchid](https://github.com/MythosOfs/Orchid) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Active fork | Auditable |
| [PokeDinner](https://git.eden-emu.dev/Franseven/PokeDinner-a-Eglantine-Fork) | GPL-3.0 | Yes, LICENSE.txt and src | Binaries | Active Forgejo | Auditable |
| [notsapinho/Eglantine](https://github.com/notsapinho/Eglantine) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Active | Auditable |
| [zortos293/Lichii](https://github.com/zortos293/Lichii) | GPL-3.0 | Yes, src and CMakeLists | Binaries (build 94/95) and Actions artifacts | Active | Auditable |
| [Frizti/Lichii](https://github.com/Frizti/Lichii) | GPL-3.0 | Yes, src and CMakeLists | Windows binaries | Active fork | Auditable |
| [rdenno/Eglantine](https://github.com/rdenno/Eglantine) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Small fork | Auditable |
| [Selevet Eglantine](https://github.com/sylvieistaken/selevet-eglantine) | GPL-3.0 | Yes, src and CMakeLists | Binaries | Tuned fork | Auditable |
| [EglantinePS5](https://github.com/heydemoura/EglantinePS5) | GPL-3.0 | Yes, src and Makefile | No release assets at check | Port | Auditable source |
| [Droplet](https://gitlab.com/seighttt/droplet) | GPL-3.0-or-later | Yes, LICENSE.txt and src | Binaries | GitLab | Auditable |
| [eden-nx2-android](https://git.eden-emu.dev/moceure/eden-nx2-android) | GPL-3.0 | Yes, LICENSE.txt and src | Tags | Forgejo | Unmaintained, points to Banana Native |
| [Banana Native](https://github.com/moceure/BananaNative) | MIT (repo); GPL-3.0-or-later (release notes) | Yes, android and dm source | APK | Active | Auditable source, license metadata inconsistent |
| [nxnative](https://github.com/seedds/nxnative) | MIT | Yes, dm and scripts source | No release assets at check | Active | Auditable source; macOS native port, not an emulator |
| [ZendNevs/Eglantine-ZendNevs](https://github.com/ZendNevs/Eglantine-ZendNevs) | None | No, only README and a workflow | Binaries plus source zip | 2 commits | Source zip only, no license |
| [Eglantine 3060Ti 16GB](https://github.com/astralbeexd/Eglantine-3060Ti-16GB) | GPL-3.0 | No, patch set only | Binary zip and hash | Small | Patch set, binary release |

## How to verify a project

1. Check the root of the repo for `LICENSE`, `LICENSE.txt` or `LICENSES/`, plus `src/` and `CMakeLists.txt` or `Makefile`.
2. Check the commit history. A repo created a few days ago with two commits and no source tree is a release channel, not an auditable project.
3. If the source is only a zip in the release, download it, build it, and compare the build with the binary you plan to run. Without a license, you cannot assume redistribution or modification rights.
4. A binary-only fork is not automatically malicious, but it cannot be reviewed, reproduced or checked against the source. Treat its performance claims as unverified and do not make it a first pick.

## What this means for the guide

All first picks publish source in the repository. Most are GPL-3.0: SmileyTatsu for Mario Kart World, Selevet or PokeDinner for Donkey Kong Bananza, notsapinho for Pokopia, Lichii, Frizti or Orchid for Ocarina of Time, and Droplet for online play. Banana Native covers Android as a native port, not an emulator; its repo is MIT while its release notes say GPL-3.0-or-later. nxnative covers macOS the same way: MIT source, no prebuilt release, and not an emulator.

Lichii now publishes numbered releases again, with build 94/95 assets for Windows, Linux and macOS. Its README still points downloads to the old zortos293/Eglantine releases page and asks for crypto donations. Use the Lichii releases tab and verify any donation address from the repository itself. Its public report hub is the largest single source of OoT reports: 202 public reports were scraped on 7 Nov and summarized in [Lichii reports](LICHII-REPORTS.md).

Anka is source-complete and auditable, with source zips and a checksum file in its release. It stays out of the first picks for now because it has one release, 7 stars, and a DK result measured on one PC. Its code and commit messages are largely AI-assisted, which the project discloses.

ZendNevs and the 3060Ti build are not first picks. ZendNevs ships a source zip but has no license and no source tree in the repo. The 3060Ti repo is a patch set with a binary release, not a full emulator fork.
