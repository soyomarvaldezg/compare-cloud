"""Validate data/services/*.yaml and data/platforms/*.yaml and render the static site into site/.

Run: uv run python scripts/build.py [--strict]
Exit code 1 on validation errors, or on stale rows when --strict is passed.
"""

import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

PROVIDER_LABELS = {
    "aws": "AWS",
    "azure": "Azure",
    "gcp": "Google Cloud",
    "databricks": "Databricks",
    "fabric": "Microsoft Fabric",
    "snowflake": "Snowflake",
}
PROVIDER_COLORS = {
    "aws": "#ff9900",
    "azure": "#0078d4",
    "gcp": "#34a853",
    "databricks": "#ff3621",
    "fabric": "#117865",
    "snowflake": "#29b5e8",
}

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Each section is one comparison table family: its own data directory and its own columns.
SECTIONS = [
    {"key": "clouds", "title": "Cloud providers", "dir": "services", "providers": ["aws", "azure", "gcp"]},
    {"key": "platforms", "title": "Data platforms", "dir": "platforms", "providers": ["databricks", "fabric", "snowflake"]},
]

STYLE = """
@font-face {
  font-family: "VD Code";
  src: url("assets/fonts/SourceCodePro.ttf") format("truetype");
  font-weight: 100 900;
  font-display: swap;
}
@font-face {
  font-family: "VD Sans";
  src: url("assets/fonts/DMSans.ttf") format("truetype");
  font-weight: 100 900;
  font-display: swap;
}
:root {
  --paper: #cfdde6;
  --paper-2: #e6edf2;
  --ink: #2d3141;
  --muted: #4a5670;
  --soft: #4a5670;
  --rule: rgba(45, 49, 65, 0.16);
  --rule-solid: #657486;
  --accent: #08829c;
  --link: #05657a;
}
* { box-sizing: border-box; }
html { -webkit-font-smoothing: antialiased; }
body {
  margin: 0;
  font-family: "VD Sans", "DM Sans", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 1.125rem;
  background: var(--paper);
  color: var(--ink);
  line-height: 1.6;
}
.serif { font-family: "VD Code", "Source Code Pro", ui-monospace, monospace; }
header.masthead {
  max-width: 1080px;
  margin: 0 auto;
  padding: 3.5rem 1.5rem 2rem;
}
.eyebrow {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  font-size: .7rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--soft);
  margin: 0 0 .9rem;
}
h1 {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  font-weight: 600;
  font-size: clamp(2rem, 5.2vw, 3rem);
  line-height: 1.05;
  margin: 0 0 .6rem;
  letter-spacing: -.01em;
}
h1 .accent-dot { color: var(--accent); }
.standfirst {
  font-size: 1.2rem;
  color: var(--muted);
  max-width: 46rem;
  margin: 0 0 1.2rem;
}
.byline {
  font-size: .85rem;
  color: var(--muted);
  margin: 0;
  padding-bottom: 1.6rem;
  border-bottom: 1px solid var(--rule-solid);
}
.byline a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--rule-solid); }
.byline a:hover { color: var(--link); border-bottom-color: var(--link); }
.byline .sep { color: var(--rule-solid); margin: 0 .5rem; }
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: .4rem 1.2rem;
  align-items: center;
  max-width: 1080px;
  margin: 0 auto;
  padding: .8rem 1.5rem;
  position: sticky;
  top: 0;
  background: var(--paper);
  border-bottom: 1px solid var(--rule);
  z-index: 5;
}
#search {
  flex: 1;
  min-width: 220px;
  padding: .45rem .1rem;
  border: none;
  border-bottom: 1px solid var(--rule-solid);
  background: transparent;
  color: var(--ink);
  font-family: inherit;
  font-size: .95rem;
}
#search:focus { outline: none; border-bottom-color: var(--accent); }
#search::placeholder { color: var(--soft); }
.chip {
  padding: .3rem 0;
  border: none;
  border-bottom: 2px solid transparent;
  background: none;
  color: var(--muted);
  cursor: pointer;
  font-size: .85rem;
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
}
.chip:hover { color: var(--ink); }
.chip.active { color: var(--ink); border-bottom-color: var(--accent); }
.chip .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
#count {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  font-size: .72rem;
  color: var(--soft);
}
main { max-width: 1080px; margin: 0 auto; padding: .5rem 1.5rem 2rem; }
section { margin-top: 2.6rem; }
h2 {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  font-weight: 600;
  font-size: 1.5rem;
  margin: 0 0 .4rem;
}
h2 .note { font-family: "VD Code", "Source Code Pro", ui-monospace, monospace; font-size: .72rem; color: var(--soft); margin-left: .5rem; }
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th {
  text-align: left;
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  padding: .8rem .75rem .5rem;
  border-bottom: 1px solid var(--rule-solid);
  color: var(--soft);
  font-weight: 500;
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .12em;
  white-space: nowrap;
}
td { padding: .7rem .75rem; vertical-align: top; border-bottom: 1px solid var(--rule); }
td.cap { font-weight: 500; }
td a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--rule-solid); }
td a:hover { color: var(--link); border-bottom-color: var(--link); }
.note { color: var(--soft); font-size: .78rem; margin-top: .15rem; }
.verified {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  color: var(--soft);
  font-size: .72rem;
  white-space: nowrap;
}
footer {
  max-width: 1080px;
  margin: 3rem auto 0;
  padding: 1.8rem 1.5rem 3rem;
  border-top: 1px solid var(--rule-solid);
  color: var(--muted);
  font-size: .85rem;
}
footer p { margin: 0 0 .7rem; max-width: 46rem; }
footer a { color: var(--link); text-decoration: none; border-bottom: 1px solid var(--rule); }
footer a:hover { border-bottom-color: var(--link); }
.group { margin-top: 3rem; }
.group-title {
  font-family: "VD Code", "Source Code Pro", ui-monospace, monospace;
  font-size: .75rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--link);
  margin: 0;
  padding-bottom: .6rem;
  border-bottom: 1px solid var(--rule-solid);
}
.group-title .note { letter-spacing: 0; text-transform: none; margin-left: .5rem; }
.chip-sep { width: 1px; height: 1rem; background: var(--rule-solid); }
.hidden { display: none !important; }
.empty { color: var(--soft); padding: 3rem 0; text-align: center; font-style: italic; }
"""

APP_JS = """
(function () {
  var search = document.getElementById("search");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("tbody tr[data-search]"));
  var groups = Array.prototype.slice.call(document.querySelectorAll(".group"));
  var count = document.getElementById("count");
  var active = "all";

  function apply() {
    var q = search.value.trim().toLowerCase();
    var visible = 0;
    rows.forEach(function (row) {
      var okProvider = active === "all" || row.getAttribute("data-providers").indexOf(active) !== -1;
      var okSearch = !q || row.getAttribute("data-search").indexOf(q) !== -1;
      var show = okProvider && okSearch;
      row.classList.toggle("hidden", !show);
      if (show) visible++;
    });
    rows.forEach(function (row) {
      var section = row.closest("section");
      if (!section) return;
      var any = section.querySelector("tbody tr:not(.hidden)");
      section.classList.toggle("hidden", !any);
    });
    groups.forEach(function (group) {
      group.classList.toggle("hidden", !group.querySelector("section:not(.hidden)"));
    });
    count.textContent = visible + " of " + rows.length + " services";
  }

  search.addEventListener("input", apply);
  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      chips.forEach(function (c) { c.classList.remove("active"); });
      chip.classList.add("active");
      active = chip.getAttribute("data-provider");
      apply();
    });
  });
  apply();
})();
"""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def load_categories(data_dir: Path) -> list[dict[str, Any]]:
    files = sorted(data_dir.glob("*.yaml"))
    if not files:
        raise SystemExit(f"No YAML files found in {data_dir}")
    categories: list[dict[str, Any]] = []
    for path in files:
        doc = yaml.safe_load(path.read_text())
        categories.append(doc)
        if not doc.get("category"):
            raise SystemExit(f"{path}: missing 'category'")
        if not isinstance(doc.get("services"), list) or not doc["services"]:
            raise SystemExit(f"{path}: 'services' must be a non-empty list")
    return categories


def load_sections(data_root: Path) -> list[dict[str, Any]]:
    return [
        {**section, "categories": load_categories(data_root / section["dir"])}
        for section in SECTIONS
    ]


def validate(sections: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for doc, providers in (
        (doc, section["providers"]) for section in sections for doc in section["categories"]
    ):
        category = doc["category"]
        for service in doc["services"]:
            where = f"{category}/{service.get('id', '?')}"
            sid = service.get("id")
            if not sid or not re.fullmatch(r"[a-z0-9-]+", str(sid)):
                errors.append(f"{where}: invalid or missing id")
            elif sid in seen_ids:
                errors.append(f"{where}: duplicate id '{sid}'")
            else:
                seen_ids.add(sid)
            if not service.get("name"):
                errors.append(f"{where}: missing name")
            verified = service.get("verified")
            if not verified:
                errors.append(f"{where}: missing verified date")
            else:
                try:
                    datetime.date.fromisoformat(str(verified))
                except ValueError:
                    errors.append(f"{where}: verified date must be ISO (YYYY-MM-DD)")
            present = [p for p in providers if service.get(p)]
            if not present:
                errors.append(f"{where}: no provider entry (need at least one of {'/'.join(providers)})")
            for key in service:
                if key in PROVIDER_LABELS and key not in providers:
                    errors.append(f"{where}: provider '{key}' does not belong in this section")
            for p in present:
                entry: Any = service[p]
                if not isinstance(entry, dict) or not entry.get("name"):
                    errors.append(f"{where}: provider '{p}' needs a name")
                url = entry.get("url")
                if url and not str(url).startswith("https://"):
                    errors.append(f"{where}: provider '{p}' url must start with https://")
    return errors


def stale_rows(categories: list[dict[str, Any]], max_age_days: int) -> list[dict[str, Any]]:
    today = datetime.date.today()
    stale: list[dict[str, Any]] = []
    for doc in categories:
        for service in doc["services"]:
            verified = datetime.date.fromisoformat(str(service["verified"]))
            age = (today - verified).days
            if age > max_age_days:
                stale.append({"category": doc["category"], "id": service["id"], "age": age})
    return stale


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def provider_cell(service: dict[str, Any], provider: str) -> str:
    entry: Any = service.get(provider)
    if not entry:
        return '<td><span class="note">—</span></td>'
    name = esc(entry["name"])
    if entry.get("url"):
        cell = f'<div class="pname"><a href="{esc(entry["url"])}" target="_blank" rel="noopener">{name}</a></div>'
    else:
        cell = f'<div class="pname">{name}</div>'
    if entry.get("note"):
        cell += f'<div class="note">{esc(entry["note"])}</div>'
    return f"<td>{cell}</td>"


def render_category(doc: dict[str, Any], providers: list[str]) -> str:
    rows = []
    for service in doc["services"]:
        providers_attr = " ".join(p for p in providers if service.get(p))
        search_blob = esc(
            " ".join(
                [service["name"]]
                + [service[p]["name"] for p in providers if service.get(p)]
            ).lower()
        )
        rows.append(
            f'<tr data-providers="{providers_attr}" data-search="{search_blob}">'
            f'<td class="cap">{esc(service["name"])}</td>'
            + "".join(provider_cell(service, p) for p in providers)
            + f'<td class="verified">{esc(service["verified"])}</td>'
            + "</tr>"
        )
    header = "".join(f"<th>{esc(PROVIDER_LABELS[p])}</th>" for p in providers)
    return (
        f'<section id="{slugify(doc["category"])}">'
        f"<h2>{esc(doc['category'])} <span class=\"note\">({len(doc['services'])})</span></h2>"
        '<div class="tablewrap"><table>'
        f"<thead><tr><th>Capability</th>{header}<th>Verified</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def render(sections: list[dict[str, Any]], out_dir: Path, max_age_days: int) -> None:
    categories = [doc for section in sections for doc in section["categories"]]
    total = sum(len(d["services"]) for d in categories)
    oldest = min(
        str(s["verified"]) for d in categories for s in d["services"]
    )
    stale = stale_rows(categories, max_age_days)

    chips = ['<button class="chip active" data-provider="all">All</button>']
    for i, section in enumerate(sections):
        if i:
            chips.append('<span class="chip-sep" aria-hidden="true"></span>')
        for p in section["providers"]:
            chips.append(
                f'<button class="chip" data-provider="{p}">'
                f'<span class="dot" style="background:{PROVIDER_COLORS[p]}"></span>{PROVIDER_LABELS[p]}</button>'
            )
    chips_html = "".join(chips)

    groups = []
    for section in sections:
        count = sum(len(d["services"]) for d in section["categories"])
        groups.append(
            f'<div class="group" id="{section["key"]}">'
            f'<h2 class="group-title">{esc(section["title"])} '
            f'<span class="note">{" · ".join(PROVIDER_LABELS[p] for p in section["providers"])} ({count})</span></h2>'
            + "".join(render_category(doc, section["providers"]) for doc in section["categories"])
            + "</div>"
        )

    stale_note = (
        f'{len(stale)} rows not re-verified in over {max_age_days} days '
        f'(oldest: {oldest}).'
        if stale
        else f'All rows verified within the last {max_age_days} days.'
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compare Cloud — AWS vs Azure vs Google Cloud, plus data platforms</title>
<meta name="description" content="An open, community-verified mapping of equivalent managed services across AWS, Azure and Google Cloud, and across the Databricks, Microsoft Fabric and Snowflake data platforms.">
<link rel="preload" href="assets/fonts/SourceCodePro.ttf" as="font" type="font/ttf" crossorigin>
<link rel="preload" href="assets/fonts/DMSans.ttf" as="font" type="font/ttf" crossorigin>
<style>{STYLE}</style>
</head>
<body>
<header class="masthead">
  <p class="eyebrow">Open source · Community verified · AWS / Azure / Google Cloud · Databricks / Fabric / Snowflake</p>
  <h1>Compare Cloud<span class="accent-dot">.</span></h1>
  <p class="standfirst">Equivalent managed services across the three major clouds and the three major data platforms — mapped in plain YAML, re-verified monthly by an automated link checker, and corrected in the open.</p>
  <p class="byline">Maintained by <a href="https://github.com/soyomarvaldezg" target="_blank" rel="noopener">@soyomarvaldezg</a><span class="sep">·</span><a href="https://links.soyomarvaldezg.com" target="_blank" rel="noopener">links.soyomarvaldezg.com</a><span class="sep">·</span><a href="https://github.com/soyomarvaldezg/compare-cloud" target="_blank" rel="noopener">source &amp; data</a></p>
</header>
<div class="controls">
  <input id="search" type="search" placeholder="Search services — try “queue”, “kubernetes”, “warehouse”…" aria-label="Search services">
  {chips_html}
  <span id="count"></span>
</div>
<main>
{chr(10).join(groups)}
<p class="empty hidden">No services match your search.</p>
</main>
<footer>
  <p>{stale_note}</p>
  <p>Dataset seeded from <a href="https://github.com/ilyas-it83/CloudComparer" target="_blank" rel="noopener">CloudComparer</a> (MIT, © Ilyas F) and re-verified against official vendor documentation. Every row carries the date it was last checked; corrections are one-line YAML edits via pull request. Product names are trademarks of their respective owners.</p>
  <p>© {datetime.date.today().year} Omar Valdez · MIT License · <a href="https://github.com/soyomarvaldezg/compare-cloud" target="_blank" rel="noopener">github.com/soyomarvaldezg/compare-cloud</a></p>
</footer>
<script>{APP_JS}</script>
</body>
</html>
"""

    out_dir.mkdir(parents=True, exist_ok=True)
    if ASSETS_DIR.is_dir():
        if (out_dir / "assets").exists():
            shutil.rmtree(out_dir / "assets")
        shutil.copytree(ASSETS_DIR, out_dir / "assets")
    (out_dir / "index.html").write_text(html)
    print(f"wrote {out_dir / 'index.html'} ({total} services, {len(categories)} categories)")
    print(f"stale (>{max_age_days}d): {len(stale)} rows, oldest verified: {oldest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("site"))
    parser.add_argument("--max-age-days", type=int, default=180)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any row is stale")
    args = parser.parse_args()

    sections = load_sections(args.data_root)
    errors = validate(sections)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    categories = [doc for section in sections for doc in section["categories"]]
    stale = stale_rows(categories, args.max_age_days)
    render(sections, args.out, args.max_age_days)

    if args.strict and stale:
        print(f"--strict: {len(stale)} stale rows exceed {args.max_age_days} days", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
