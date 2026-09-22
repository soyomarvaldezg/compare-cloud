"""One-time converter: seed data/services/*.yaml from CloudComparer (MIT).

Source: https://github.com/ilyas-it83/CloudComparer (c) Ilyas F, MIT License.
Prunes to AWS/Azure/GCP, applies documented renames, rewrites retired doc domains.
Run: uv run python scripts/convert_cloudcomparer.py --input .crush/cloudservices.yml
"""

import argparse
import datetime
import re
from pathlib import Path
from typing import Any

import yaml

PROVIDERS = ["aws", "azure", "google"]
OUTPUT_KEYS = {"aws": "aws", "azure": "azure", "google": "gcp"}

RENAMES = {
    "azure active directory": "Microsoft Entra ID",
    "azure active directory (aad)": "Microsoft Entra ID",
    "azure security center": "Microsoft Defender for Cloud",
    "azure operations management suite (oms)": "Azure Monitor",
    "google stackdriver": "Google Cloud Operations Suite",
    "aws cloudwatch": "Amazon CloudWatch",
}

RENAMED_URLS = {
    "https://learn.microsoft.com/azure/active-directory/": "https://learn.microsoft.com/en-us/entra/fundamentals/what-is-entra",
    "https://learn.microsoft.com/azure/security-center/": "https://learn.microsoft.com/azure/defender-for-cloud/defender-for-cloud-introduction",
}

CANONICAL_CATEGORIES = {
    "compute": "Compute",
    "hybrid-cloud": "Compute",
    "storage": "Storage",
    "database": "Database",
    "networking": "Networking & Content Delivery",
    "networking-content-delivery": "Networking & Content Delivery",
    "security-identity-compliance": "Security, Identity & Compliance",
    "management-tools": "Management & Governance",
    "automated-cloud-management-service": "Management & Governance",
    "big-data-advanced-analytics": "Analytics",
    "artificial-intelligence-machine-learning": "AI & Machine Learning",
    "artificial-intelligence": "AI & Machine Learning",
    "developer-tools": "Developer Tools",
    "development-testing": "Developer Tools",
    "game-development": "Developer Tools",
    "robotics-development": "Developer Tools",
    "migration-services": "Migration & Transfer",
    "application-discovery-services": "Migration & Transfer",
    "disaster-recovery-services": "Migration & Transfer",
    "application-services": "Application Integration",
    "mobile-services": "Mobile",
    "internet-of-things": "Internet of Things",
    "business-productivity": "Business Productivity",
    "software-marketplace": "Business Productivity",
}

CATEGORY_ORDER = list(dict.fromkeys(CANONICAL_CATEGORIES.values()))


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unnamed"


def clean_url(url: str) -> str | None:
    if not url:
        return None
    url = url.strip().replace("http://", "https://")
    url = url.replace("docs.microsoft.com", "learn.microsoft.com")
    return RENAMED_URLS.get(url, url)


def provider_entries(row_service: list[Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for entry in row_service or []:
        for key, items in entry.items():
            if key not in PROVIDERS or not isinstance(items, list):
                continue
            named = [i for i in items if i.get("name")]
            if not named:
                continue
            primary = named[0]
            value = {
                "name": primary["name"].strip(),
                "url": clean_url(primary.get("ref") or ""),
            }
            if len(named) > 1:
                extras = ", ".join(i["name"].strip() for i in named[1:])
                value["note"] = f"also: {extras}"
            found[key] = value
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--outdir", type=Path, default=Path("data/services"))
    parser.add_argument("--verified-date", default=str(datetime.date.today()))
    args = parser.parse_args()

    raw = yaml.safe_load(args.input.read_text())
    rows = raw.get("services", [])

    categories: dict[str, list[dict[str, Any]]] = {}
    used_ids: set[str] = set()
    applied_renames: list[str] = []
    skipped = 0

    for row in rows:
        providers = provider_entries(row.get("service"))
        if not providers:
            skipped += 1
            continue

        subcategory = (row.get("subcategory") or "").strip() or "General"
        name = subcategory
        lowered = name.lower()
        if lowered in RENAMES:
            applied_renames.append(f"{name} -> {RENAMES[lowered]}")
            name = RENAMES[lowered]

        service_id = slugify(subcategory)
        base_id = service_id
        counter = 2
        while service_id in used_ids:
            service_id = f"{base_id}-{counter}"
            counter += 1
        used_ids.add(service_id)

        entry = {
            "id": service_id,
            "name": name,
            "verified": args.verified_date,
        }
        for src, dst in OUTPUT_KEYS.items():
            if src in providers:
                entry[dst] = providers[src]

        original = (row.get("category") or "Other").strip() or "Other"
        category = CANONICAL_CATEGORIES.get(
            slugify(original), original
        )
        categories.setdefault(category, []).append(entry)

    args.outdir.mkdir(parents=True, exist_ok=True)
    for old_file in args.outdir.glob("*.yaml"):
        old_file.unlink()

    total = 0
    ordered = {name: categories[name] for name in CATEGORY_ORDER if name in categories}
    for name, services in ordered.items():
        doc = {
            "category": name,
            "description": "",
            "services": services,
        }
        path = args.outdir / f"{slugify(name)}.yaml"
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        total += len(services)
        print(f"{path}: {len(services)} services")

    print(f"\ntotal: {total} services in {len(categories)} categories, {skipped} rows skipped (no AWS/Azure/GCP entry)")
    if applied_renames:
        print("\nrenames applied:")
        for r in applied_renames:
            print(f"  {r}")


if __name__ == "__main__":
    main()
