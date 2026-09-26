"""Staleness detector: check every service URL in data/services/*.yaml and data/platforms/*.yaml.

Classifies each link as OK, REDIRECTED (docs moved or product renamed — the
final URL/title usually reveal the new name), BROKEN (4xx/5xx), or ERROR.

Run: uv run python scripts/check_links.py [--limit 25] [--report report.md]
Exit code 1 if any BROKEN link is found (use --no-fail to disable).
"""

import argparse
import concurrent.futures
import datetime
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from build import SECTIONS

USER_AGENT = "compare-cloud-link-checker/0.1 (+https://github.com/soyomarvaldezg/compare-cloud)"
TIMEOUT = 20
ATTEMPTS = 2
CONCURRENCY = 8
RETRYABLE = {429, 500, 502, 503, 504}


def collect_urls(data_root: Path) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for section, path in (
        (section, path) for section in SECTIONS for path in sorted((data_root / section["dir"]).glob("*.yaml"))
    ):
        doc = yaml.safe_load(path.read_text())
        category = doc.get("category", path.stem)
        for service in doc.get("services", []):
            for provider in section["providers"]:
                entry: Any = service.get(provider)
                if isinstance(entry, dict) and entry.get("url"):
                    targets.append(
                        {
                            "category": category,
                            "service": service.get("id", "?"),
                            "provider": provider,
                            "url": str(entry["url"]),
                        }
                    )
    return targets


class RedirectTracker(urllib.request.HTTPRedirectHandler):
    def __init__(self) -> None:
        self.chain: list[tuple[int, str]] = []

    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any) -> Any:
        self.chain.append((code, headers.get("Location", "")))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url(url: str) -> dict[str, Any]:
    result: dict[str, Any] = {"url": url, "status": None, "final_url": url, "title": None, "error": None}
    tracker = RedirectTracker()
    opener = urllib.request.build_opener(tracker)
    opener.addheaders = [("User-Agent", USER_AGENT)]

    for attempt in range(ATTEMPTS):
        try:
            response = opener.open(url, timeout=TIMEOUT)
            body = response.read(400_000).decode("utf-8", "ignore")
            match = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            result["status"] = response.status
            result["final_url"] = response.geturl()
            if match:
                result["title"] = re.sub(r"\s+", " ", match.group(1)).strip()[:120]
            if tracker.chain:
                result["redirects"] = [loc for _, loc in tracker.chain]
            return result
        except urllib.error.HTTPError as e:
            result["status"] = e.code
            if e.code in RETRYABLE and attempt < ATTEMPTS - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return result
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"
            if attempt < ATTEMPTS - 1:
                time.sleep(2)
                continue
            return result
    return result


def classify(result: dict[str, Any]) -> str:
    if result["error"]:
        return "ERROR"
    status = result["status"] or 0
    if 200 <= status < 300 and result.get("redirects"):
        return "REDIRECTED"
    if 200 <= status < 300:
        return "OK"
    if 300 <= status < 400:
        return "REDIRECTED"
    return "BROKEN"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, help="write a markdown report to this path")
    parser.add_argument("--limit", type=int, help="check only the first N URLs (testing)")
    parser.add_argument("--no-fail", action="store_true", help="always exit 0")
    args = parser.parse_args()

    targets = collect_urls(args.data_root)
    if args.limit:
        targets = targets[: args.limit]

    print(f"checking {len(targets)} URLs with concurrency {CONCURRENCY}…")
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {pool.submit(check_url, t["url"]): t for t in targets}
        done = 0
        for future in concurrent.futures.as_completed(futures):
            target = futures[future]
            outcome = future.result()
            outcome.update(target)
            results.append(outcome)
            done += 1
            if done % 25 == 0 or done == len(targets):
                print(f"  {done}/{len(targets)}")

    for result in results:
        result["class"] = classify(result)

    counts = {"OK": 0, "REDIRECTED": 0, "BROKEN": 0, "ERROR": 0}
    for result in results:
        counts[result["class"]] += 1

    print(f"\nresults: {counts['OK']} ok, {counts['REDIRECTED']} redirected, {counts['BROKEN']} broken, {counts['ERROR']} errors")

    by_class = {"REDIRECTED": [], "BROKEN": [], "ERROR": []}
    for result in results:
        if result["class"] in by_class:
            by_class[result["class"]].append(result)

    lines = [
        f"# Staleness report — {datetime.date.today().isoformat()}",
        "",
        f"Checked {len(results)} URLs: {counts['OK']} ok, {counts['REDIRECTED']} redirected, "
        f"{counts['BROKEN']} broken, {counts['ERROR']} errors.",
        "",
    ]
    for label, items in by_class.items():
        if not items:
            continue
        lines.append(f"## {label} ({len(items)})")
        lines.append("")
        for r in items:
            lines.append(f"### `{r['category']}` / `{r['service']}` ({r['provider']})")
            lines.append(f"- URL: {r['url']}")
            if r["class"] == "REDIRECTED":
                lines.append(f"- Redirects to: {r['final_url']}")
                if r.get("title"):
                    lines.append(f"- Final page title: {r['title']}")
            elif r["status"]:
                lines.append(f"- HTTP status: {r['status']}")
            else:
                lines.append(f"- Error: {r['error']}")
            lines.append("")

    report = "\n".join(lines)
    if args.report:
        args.report.write_text(report)
        print(f"report written to {args.report}")

    if by_class["BROKEN"] and not args.no_fail:
        print(f"FAIL: {counts['BROKEN']} broken links", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
