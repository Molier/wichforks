(() => {
  "use strict";

  const PLATFORMS = [
    ["", "Any platform", null],
    ["windows", "Windows", /windows/],
    ["linux", "Linux / Steam Deck", /linux|steamos|steam deck/],
    ["macos", "macOS", /macos|\bmac\b/],
    ["android", "Android", /android/],
    ["ios", "iPhone / iPad", /iphone|ipad|\bios\b/],
    ["ps5", "PS5", /ps5/],
  ];
  const VENDORS = ["NVIDIA", "AMD", "Intel"];
  const STATUS_LABEL = { perfect: "Perfect", playable: "Playable", broken: "Broken", "wont-boot": "Won't boot" };
  const DAY = 86400000;

  const $ = (id) => document.getElementById(id);

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  const link = (href, text) => el("a", { href, rel: "noopener" }, text);
  const num = (value) => (typeof value === "number" ? value.toLocaleString("en-US") : "–");
  const day = (iso) => (iso ? iso.slice(0, 10) : "–");
  const ageDays = (iso) => (iso ? (Date.now() - Date.parse(iso)) / DAY : null);

  function ago(iso) {
    const days = ageDays(iso);
    if (days === null || Number.isNaN(days)) return "";
    if (days < 0) return "just now";
    const hours = days * 24;
    if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min ago`;
    if (hours < 48) return `${Math.round(hours)} h ago`;
    return `${Math.round(days)} days ago`;
  }

  function wordIn(needle, haystack) {
    const escaped = needle.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(haystack.toLowerCase());
  }

  let data;
  let projects = [];
  let showOthers = false;
  const tableSort = { key: "released", dir: -1 };

  function prepare() {
    const forks = data.forks.map((fork) => {
      const native = /native/i.test(fork.role || "");
      return { ...fork, group: native ? "native" : "emulator", kind: fork.role || (native ? "native port" : "emulator fork") };
    });
    const ports = data.ports.map((port) => ({ ...port, group: "native", isPort: true }));
    projects = [...forks, ...ports].map((project, index) => {
      const status = data.status[project.id] || {};
      const games = project.isPort
        ? [project.game]
        : data.games
            .filter((game) => (project.best_for || []).some((text) => [game.name, ...game.aliases].some((alias) => wordIn(alias, text))))
            .map((game) => game.id);
      const github = status.host === "GitHub" && status.full_name;
      return {
        ...project,
        index,
        status,
        games,
        url: status.html_url || project.repo,
        releasesUrl: github ? `https://github.com/${status.full_name}/releases` : project.releases || project.repo,
        release: status.release || null,
        dead: status.state === "gone" || status.state === "archived",
      };
    });
  }

  function reportsFor(project, gameId) {
    return data.reports.filter((report) => report.project === project.id && (!gameId || report.game === gameId));
  }

  function matchesPlatform(project, key) {
    const entry = PLATFORMS.find((row) => row[0] === key);
    if (!entry || !entry[2]) return true;
    return entry[2].test((project.platforms || []).join(" | ").toLowerCase());
  }

  function matchesGpu(project, vendor) {
    if (!vendor) return true;
    const text = (project.gpu || []).join(" | ").toLowerCase();
    const named = VENDORS.filter((name) => text.includes(name.toLowerCase()));
    return named.length === 0 || named.includes(vendor);
  }

  function stateChips(project) {
    const chips = [];
    const { status } = project;
    if (status.state === "gone") chips.push(el("span", { class: "chip bad", text: "repository gone" }));
    if (status.state === "archived") chips.push(el("span", { class: "chip warn", text: "archived" }));
    if (status.state === "renamed") chips.push(el("span", { class: "chip warn", text: `now ${status.full_name}` }));
    if (project.source_in_repo === false) chips.push(el("span", { class: "chip warn", text: "no source tree" }));
    return chips;
  }

  function releaseLine(project) {
    const { release, status } = project;
    if (!status.state) return el("p", { class: "line", text: "Live status not available." });
    if (status.state === "unknown") return el("p", { class: "line", text: "Live status could not be read." });
    if (status.state === "gone") return el("p", { class: "line", text: `The repository ${status.listed} no longer exists.` });
    if (!release) {
      return el("p", { class: "line" }, el("span", { class: "dot" }), "No published release. Last push ", ago(status.pushed_at) || "unknown", ".");
    }
    const days = ageDays(release.date);
    const dot = days < 2 ? "dot ok" : days < 7 ? "dot warn" : "dot";
    return el(
      "p",
      { class: "line" },
      el("span", { class: dot }),
      "Latest release ",
      el("strong", { text: release.tag || "untagged" }),
      `, ${ago(release.date)}`,
      release.prerelease ? " (pre-release)" : "",
      release.downloads ? `, ${num(release.downloads)} downloads` : "",
      status.stable_release ? `. Latest full release ${status.stable_release.tag}, ${ago(status.stable_release.date)}` : "",
      "."
    );
  }

  function trustLine(project) {
    const { status } = project;
    const parts = [`Licence: ${project.license || status.license || "none stated"}`];
    if (status.tree) {
      const files = status.tree.build_files.length ? status.tree.build_files.join(", ") : "no build files";
      parts.push(`top level: ${files}, ${status.tree.code_dirs} code folders`);
    }
    if (typeof status.commits_7d === "number") parts.push(`${num(status.commits_7d)} commits in 7 days`);
    if (status.created_at) parts.push(`repository created ${day(status.created_at)}`);
    if (typeof status.stars === "number") parts.push(`${num(status.stars)} stars`);
    return el("p", { class: "line", text: parts.join(" · ") + "." });
  }

  function reportLine(project, game) {
    const reports = reportsFor(project, game && game.id);
    const title = `[Report] ${game ? game.name + " - " : ""}${project.name}`;
    const query = new URLSearchParams({ template: "experience-report.yml", title });
    if (game) query.set("game", game.name);
    const reportUrl = `https://github.com/${data.repo}/issues/new?${query}`;
    let summary = game ? "No reports for this game yet." : "No reports yet.";
    if (reports.length) {
      const counts = {};
      let thumbs = 0;
      for (const report of reports) {
        const key = STATUS_LABEL[report.status] || "Unsorted";
        counts[key] = (counts[key] || 0) + 1;
        thumbs += report.thumbs || 0;
      }
      const tally = Object.entries(counts).map(([label, count]) => `${count} ${label.toLowerCase()}`).join(", ");
      summary = `${reports.length} ${reports.length === 1 ? "report" : "reports"}: ${tally}${thumbs ? `, ${thumbs} thumbs-up` : ""}.`;
    }
    return el("p", { class: "actions" }, el("span", { text: summary }), link(reportUrl, "Report your result"));
  }

  function card(project, game) {
    const chips = [
      el("span", { class: "chip", text: project.kind }),
      project.state ? el("span", { class: `chip ${project.state === "playable" ? "ok" : "warn"}`, text: project.state }) : null,
      el("span", { class: "chip", text: project.confidence }),
      ...stateChips(project),
    ];
    return el(
      "article",
      { class: project.dead ? "card dim" : "card" },
      el("h4", {}, link(project.url, project.name)),
      el("div", { class: "chips" }, chips),
      releaseLine(project),
      el("p", { class: "line" }, el("strong", { text: "Runs on: " }), (project.platforms || []).join(", "), project.gpu && project.gpu.length ? `. GPU: ${project.gpu.join(", ")}` : "", "."),
      project.best_for ? el("p", { class: "line" }, el("strong", { text: "Listed for: " }), project.best_for.join(", "), ".") : null,
      project.game_version ? el("p", { class: "line" }, el("strong", { text: "Game version: " }), project.game_version, ".") : null,
      trustLine(project),
      project.notes ? el("details", {}, el("summary", { text: "Notes from the guide" }), el("p", { text: project.notes })) : null,
      el("p", { class: "actions" }, project.dead ? null : link(project.releasesUrl, "Releases"), link(project.url, "Repository")),
      reportLine(project, game)
    );
  }

  function ordered(list, order, gameId) {
    const sorted = [...list];
    if (order === "release") sorted.sort((a, b) => ((b.release && b.release.date) || "").localeCompare((a.release && a.release.date) || ""));
    else if (order === "reports") sorted.sort((a, b) => reportsFor(b, gameId).length - reportsFor(a, gameId).length || a.index - b.index);
    else sorted.sort((a, b) => a.index - b.index);
    return sorted.sort((a, b) => Number(a.dead) - Number(b.dead));
  }

  function renderResults() {
    const gameId = $("f-game").value;
    const platform = $("f-platform").value;
    const vendor = $("f-gpu").value;
    const order = $("f-order").value;
    const game = data.games.find((entry) => entry.id === gameId) || null;
    const fits = projects.filter((project) => matchesPlatform(project, platform) && matchesGpu(project, vendor));
    const listed = game ? fits.filter((project) => project.games.includes(game.id)) : fits;
    const others = game ? fits.filter((project) => !project.games.includes(game.id) && project.group === "emulator") : [];

    const root = $("results");
    root.replaceChildren();
    const heading = game ? `Options for ${game.name}` : "All listed projects";
    root.append(el("h2", { text: `${heading} (${listed.length})` }));
    if (game && game.guide) {
      root.append(el("p", { class: "hint" }, "Settings and build notes: ", link(`https://github.com/${data.repo}/blob/main/${game.guide}`, game.guide), "."));
    }
    if (!listed.length) {
      root.append(el("p", { class: "empty", text: "Nothing in the guide matches these filters." }));
    }
    for (const [group, label] of [["emulator", "Emulator forks"], ["native", "Native ports (no emulator)"]]) {
      const members = ordered(listed.filter((project) => project.group === group), order, gameId);
      if (!members.length) continue;
      root.append(el("h3", { class: "group", text: `${label} (${members.length})` }));
      root.append(el("div", { class: "cards" }, members.map((project) => card(project, game))));
    }
    if (others.length) {
      root.append(
        el(
          "p",
          { class: "more" },
          `${others.length} other emulator ${others.length === 1 ? "fork is" : "forks are"} not listed for this game in the guide. `,
          el("button", { type: "button", onclick: () => { showOthers = !showOthers; renderResults(); } }, showOthers ? "Hide them" : "Show them")
        )
      );
      if (showOthers) root.append(el("div", { class: "cards" }, ordered(others, order, gameId).map((project) => card(project, game))));
    }
    const hash = new URLSearchParams();
    if (gameId) hash.set("game", gameId);
    if (platform) hash.set("platform", platform);
    if (vendor) hash.set("gpu", vendor);
    history.replaceState(null, "", hash.toString() ? `#${hash}` : location.pathname + location.search);
  }

  function renderAttention() {
    const items = [];
    for (const project of projects) {
      const { status, release } = project;
      const name = () => el("strong", { text: project.name });
      if (status.state === "gone") items.push([name(), `: the listed repository ${status.listed} no longer exists.`]);
      if (status.state === "renamed") items.push([name(), `: listed as ${status.listed}, now `, link(status.html_url, status.full_name), "."]);
      if (status.state === "archived") items.push([name(), ": the repository is archived."]);
      const guide = project.latest_release;
      if (guide && guide.tag && release && release.tag && guide.tag !== release.tag) {
        items.push([name(), `: the guide lists ${guide.tag} (${guide.date || "no date"}); the newest release is ${release.tag} (${day(release.date)}).`]);
      }
      const newest = [release && release.date, status.pushed_at].filter(Boolean).sort().pop();
      if (newest && !project.dead && ageDays(newest) >= 7) items.push([name(), `: no release or push for ${Math.round(ageDays(newest))} days.`]);
    }
    $("attention").hidden = items.length === 0;
    $("attention-summary").textContent = `${items.length} ${items.length === 1 ? "difference" : "differences"} between the guide's data files and the repositories`;
    $("attention-list").replaceChildren(...items.map((parts) => el("li", {}, parts)));
  }

  const COLUMNS = [
    ["name", "Project", (p) => p.name.toLowerCase(), (p) => link(p.url, p.name)],
    ["group", "Type", (p) => p.group, (p) => (p.group === "native" ? "Native port" : "Emulator fork")],
    ["tag", "Latest release", (p) => (p.release && p.release.tag) || "", (p) => (p.release && p.release.tag) || "–"],
    ["released", "Released", (p) => (p.release && p.release.date) || "", (p) => day(p.release && p.release.date)],
    ["pushed", "Last push", (p) => p.status.pushed_at || "", (p) => day(p.status.pushed_at)],
    ["commits", "Commits, 7 days", (p) => p.status.commits_7d ?? -1, (p) => num(p.status.commits_7d), true],
    ["stars", "Stars", (p) => p.status.stars ?? -1, (p) => num(p.status.stars), true],
    ["downloads", "Downloads, latest", (p) => (p.release && p.release.downloads) || 0, (p) => num(p.release ? p.release.downloads : undefined), true],
    ["license", "Licence", (p) => (p.license || p.status.license || "").toLowerCase(), (p) => p.license || p.status.license || "–"],
    ["state", "Repository", (p) => p.status.state || "", (p) => p.status.state || "not checked"],
  ];

  function renderTable() {
    const table = $("table");
    const column = COLUMNS.find((entry) => entry[0] === tableSort.key);
    const rows = [...projects].sort((a, b) => {
      const [x, y] = [column[2](a), column[2](b)];
      return (x < y ? -1 : x > y ? 1 : 0) * tableSort.dir;
    });
    table.tHead.replaceChildren(
      el("tr", {}, COLUMNS.map(([key, label, , , numeric]) =>
        el("th", { class: numeric ? "num" : null, "aria-sort": key === tableSort.key ? (tableSort.dir === 1 ? "ascending" : "descending") : null },
          el("button", { type: "button", onclick: () => {
            tableSort.dir = tableSort.key === key ? -tableSort.dir : numeric || key === "released" || key === "pushed" ? -1 : 1;
            tableSort.key = key;
            renderTable();
          } }, label + (key === tableSort.key ? (tableSort.dir === 1 ? " ↑" : " ↓") : ""))
        )
      ))
    );
    table.tBodies[0].replaceChildren(
      ...rows.map((project) => el("tr", {}, COLUMNS.map(([, , , cell, numeric]) => el("td", { class: numeric ? "num" : null }, cell(project)))))
    );
  }

  function renderReports() {
    const reports = [...data.reports].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    $("reports").hidden = reports.length === 0;
    if (!reports.length) return;
    const names = Object.fromEntries(projects.map((project) => [project.id, project.name]));
    const head = ["Date", "Game", "Project", "Build", "Result", "GPU", "FPS", "Thumbs-up", "Source"];
    const table = $("report-table");
    table.tHead.replaceChildren(el("tr", {}, head.map((label) => el("th", { text: label }))));
    table.tBodies[0].replaceChildren(
      ...reports.map((report) =>
        el("tr", {},
          el("td", { text: report.date || "–" }),
          el("td", { text: report.game_name || "–" }),
          el("td", { text: names[report.project] || "not matched" }),
          el("td", { class: "wide", text: report.build || "–" }),
          el("td", { text: STATUS_LABEL[report.status] || "–" }),
          el("td", { text: report.gpu || "–" }),
          el("td", { text: report.fps ?? "–" }),
          el("td", { class: "num", text: report.thumbs || 0 }),
          el("td", {}, report.url ? link(report.url, report.reviewed ? "reviewed" : "unreviewed issue") : report.reviewed ? "reviewed" : "–")
        )
      )
    );
  }

  function renderLookalikes() {
    const names = Object.fromEntries(projects.map((project) => [project.id, project.name]));
    $("lookalikes").hidden = data.lookalikes.length === 0;
    $("lookalike-list").replaceChildren(
      ...data.lookalikes.map((row) => {
        const status = data.status[`lookalike:${row.repo}`] || {};
        const slug = row.repo.replace("https://github.com/", "");
        const state = status.state === "gone" ? " This repository has since been removed." : "";
        return el("li", {}, el("code", { text: slug }), ` imitates ${names[row.imitates] || row.imitates}. ${row.facts}${state} Checked ${row.checked}.`);
      })
    );
  }

  function renderMeta() {
    const modes = {
      full: "",
      light: " Light status (no API token): commit counts and source checks are missing.",
      offline: " Built without network access: live status is missing.",
    };
    const unknown = projects.filter((project) => project.status.state === "unknown").length;
    $("meta").textContent =
      `Status read ${data.generated.replace("T", " ").replace("Z", " UTC")} (${ago(data.generated)}). ` +
      `${data.forks.length} forks, ${data.ports.length} native ports, ${data.reports.length} reports.` +
      (modes[data.status_mode] || "") +
      (unknown ? ` ${unknown} repositories could not be read.` : "");
    $("guide-link").href = `https://github.com/${data.repo}#readme`;
  }

  function fillSelect(id, options, selected) {
    $(id).replaceChildren(...options.map(([value, label]) => el("option", { value, selected: value === selected, text: label })));
    $(id).addEventListener("change", () => { showOthers = false; renderResults(); });
  }

  async function main() {
    try {
      const response = await fetch("data.json", { cache: "no-cache" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      $("meta").textContent = `The status data could not be loaded (${error.message}).`;
      return;
    }
    prepare();
    const hash = new URLSearchParams(location.hash.slice(1));
    fillSelect("f-game", [["", "All games"], ...data.games.map((game) => [game.id, game.name])], hash.get("game") || "");
    fillSelect("f-platform", PLATFORMS.map(([value, label]) => [value, label]), hash.get("platform") || "");
    fillSelect("f-gpu", [["", "Any GPU"], ...VENDORS.map((vendor) => [vendor, vendor])], hash.get("gpu") || "");
    $("f-order").addEventListener("change", renderResults);
    renderMeta();
    renderResults();
    renderAttention();
    renderTable();
    renderReports();
    renderLookalikes();
  }

  main();
})();
