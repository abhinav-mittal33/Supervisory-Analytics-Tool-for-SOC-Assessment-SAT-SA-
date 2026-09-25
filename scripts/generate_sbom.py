"""Build Order Step 14: a basic software bill of materials (Section 18) — every
package actually installed in the project's virtualenv, with its version and license,
generated from the environment itself (importlib.metadata, stdlib — no new dependency
for this), not hand-maintained or guessed.
"""
import json
from importlib import metadata
from pathlib import Path

OUT_PATH = Path(__file__).parent.parent / "docs" / "sbom.json"


def _license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    license_expr = meta.get("License-Expression")
    if license_expr:
        return license_expr

    license_field = meta.get("License")
    # Some packages (e.g. ptyprocess) literally put the string "UNKNOWN" in this
    # field rather than leaving it absent — that must NOT short-circuit past the
    # classifier fallback below, which is where their real license actually is.
    if license_field and license_field.strip().upper() != "UNKNOWN":
        if len(license_field) < 200:
            return license_field
        # Some packages (e.g. pgmpy) put the full license text here instead of a
        # short identifier — the license name is reliably in the first line.
        first_line = license_field.strip().splitlines()[0].strip()
        if first_line:
            return first_line

    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()

    return "UNKNOWN"


def main() -> None:
    packages = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or dist.metadata.get("Summary") or "UNKNOWN"
        packages.append({"name": name, "version": dist.version, "license": _license(dist)})

    packages.sort(key=lambda p: p["name"].lower())
    unknown = [p["name"] for p in packages if p["license"] == "UNKNOWN"]

    sbom = {
        "generated_by": "scripts/generate_sbom.py",
        "python_version": __import__("sys").version,
        "package_count": len(packages),
        "packages": packages,
        "licenses_needing_manual_review": unknown,
    }
    OUT_PATH.write_text(json.dumps(sbom, indent=2))
    print(f"wrote {OUT_PATH} — {len(packages)} packages, {len(unknown)} with unresolved license metadata")
    if unknown:
        print("  needs manual review:", ", ".join(unknown))


if __name__ == "__main__":
    main()
