"""Validate data/services/*.yaml and render the static site into site/.

Run: uv run python scripts/build.py [--strict]
Exit code 1 on validation errors, or on stale rows when --strict is passed.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Any

import yaml

PROVIDERS = ["aws", "azure", "gcp"]
PROVIDER_LABELS = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud"}
PROVIDER_COLORS = {"aws": "#ff9900", "azure": "#0078d4", "gcp": "#34a853"}

STYLE = """
:root {
  --paper: #f5f5f5;
  --paper-2: #ececec;
  --ink: #2d3142;
  --muted: #4f5d75;
  --soft: #7a8399;
  --rule: rgba(45, 49, 66, 0.12);
  --rule-solid: #bfc0c0;
  --accent: #eb6c36;
  --link: #2e5aa8;
}
* { box-sizing: border-box; }
html { -webkit-font-smoothing: antialiased; }
body {
  margin: 0;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  background: var(--paper);
  color: var(--ink);
  line-height: 1.55;
}
.serif { font-family: "Instrument Serif", Georgia, "Times New Roman", serif; }
header.masthead {
  max-width: 1080px;
  margin: 0 auto;
  padding: 3.5rem 1.5rem 2rem;
}
.eyebrow {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .7rem;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--soft);
  margin: 0 0 .9rem;
}
h1 {
  font-family: "Instrument Serif", Georgia, "Times New Roman", serif;
  font-weight: 400;
  font-size: 3.2rem;
  line-height: 1.05;
  margin: 0 0 .6rem;
}
h1 .accent-dot { color: var(--accent); }
.standfirst {
  font-size: 1.05rem;
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
  font-family: inherit;
}
.chip:hover { color: var(--ink); }
.chip.active { color: var(--ink); border-bottom-color: var(--accent); }
.chip .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
#count {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .72rem;
  color: var(--soft);
}
main { max-width: 1080px; margin: 0 auto; padding: .5rem 1.5rem 2rem; }
section { margin-top: 2.6rem; }
h2 {
  font-family: "Instrument Serif", Georgia, "Times New Roman", serif;
  font-weight: 400;
  font-size: 1.55rem;
  margin: 0 0 .4rem;
}
h2 .note { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .72rem; color: var(--soft); margin-left: .5rem; }
.tablewrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th {
  text-align: left;
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
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
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
.hidden { display: none !important; }
.empty { color: var(--soft); padding: 3rem 0; text-align: center; font-style: italic; }
"""

APP_JS = """
(function () {
  var search = document.getElementById("search");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var rows = Array.prototype.slice.call(document.querySelectorAll("tbody tr[data-search]"));
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


def validate(categories: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for doc in categories:
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
            present = [p for p in PROVIDERS if service.get(p)]
            if not present:
                errors.append(f"{where}: no provider entry (need at least one of aws/azure/gcp)")
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


def render(categories: list[dict[str, Any]], out_dir: Path, max_age_days: int) -> None:
    total = sum(len(d["services"]) for d in categories)
    oldest = min(
        str(s["verified"]) for d in categories for s in d["services"]
    )
    stale = stale_rows(categories, max_age_days)

    chips = ['<button class="chip active" data-provider="all">All</button>']
    for p in PROVIDERS:
        chips.append(
            f'<button class="chip" data-provider="{p}">'
            f'<span class="dot" style="background:{PROVIDER_COLORS[p]}"></span>{PROVIDER_LABELS[p]}</button>'
        )
    chips_html = "".join(chips)

    sections = []
    for doc in categories:
        rows = []
        for service in doc["services"]:
            providers_attr = " ".join(p for p in PROVIDERS if service.get(p))
            search_blob = esc(
                " ".join(
                    [service["name"]]
                    + [service[p]["name"] for p in PROVIDERS if service.get(p)]
                ).lower()
            )
            rows.append(
                f'<tr data-providers="{providers_attr}" data-search="{search_blob}">'
                f'<td class="cap">{esc(service["name"])}</td>'
                + "".join(provider_cell(service, p) for p in PROVIDERS)
                + f'<td class="verified">{esc(service["verified"])}</td>'
                + "</tr>"
            )
        rows_html = "".join(rows)
        sections.append(
            f'<section id="{slugify(doc["category"])}">'
            f"<h2>{esc(doc['category'])} <span class=\"note\">({len(doc['services'])})</span></h2>"
            '<div class="tablewrap"><table>'
            "<thead><tr><th>Capability</th><th>AWS</th><th>Azure</th><th>Google Cloud</th><th>Verified</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table></div></section>"
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
<title>Compare Cloud — AWS vs Azure vs Google Cloud</title>
<meta name="description" content="An open, community-verified mapping of equivalent managed services across AWS, Azure and Google Cloud.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>{STYLE}</style>
</head>
<body>
<header class="masthead">
  <p class="eyebrow">Open source · Community verified · AWS / Azure / Google Cloud</p>
  <h1>Compare Cloud<span class="accent-dot">.</span></h1>
  <p class="standfirst">Equivalent managed services across the three major clouds — mapped in plain YAML, re-verified monthly by an automated link checker, and corrected in the open.</p>
  <p class="byline">Maintained by <a href="https://github.com/soyomarvaldezg" target="_blank" rel="noopener">@soyomarvaldezg</a><span class="sep">·</span><a href="https://links.soyomarvaldezg.com" target="_blank" rel="noopener">links.soyomarvaldezg.com</a><span class="sep">·</span><a href="https://github.com/soyomarvaldezg/compare-cloud" target="_blank" rel="noopener">source &amp; data</a></p>
</header>
<div class="controls">
  <input id="search" type="search" placeholder="Search services — try “queue”, “kubernetes”, “blob”…" aria-label="Search services">
  {chips_html}
  <span id="count"></span>
</div>
<main>
{chr(10).join(sections)}
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
    (out_dir / "index.html").write_text(html)
    print(f"wrote {out_dir / 'index.html'} ({total} services, {len(categories)} categories)")
    print(f"stale (>{max_age_days}d): {len(stale)} rows, oldest verified: {oldest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/services"))
    parser.add_argument("--out", type=Path, default=Path("site"))
    parser.add_argument("--max-age-days", type=int, default=180)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any row is stale")
    args = parser.parse_args()

    categories = load_categories(args.data_dir)
    errors = validate(categories)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    stale = stale_rows(categories, args.max_age_days)
    render(categories, args.out, args.max_age_days)

    if args.strict and stale:
        print(f"--strict: {len(stale)} stale rows exceed {args.max_age_days} days", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
