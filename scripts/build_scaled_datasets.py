"""Build Order Step 4: generate both full-scale, structurally distinct CSE profiles
and write them to data/scaled/, alongside their ground-truth sidecars.
"""
import json
from pathlib import Path

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED, SMALL_CSE_SCALED
from satsa.ocel import json_io, sqlite_io, validate

OUT_DIR = Path(__file__).parent.parent / "data" / "scaled"
REQUIRED_OBJECT_TYPES = {"Alert", "Case", "Analyst", "Queue", "Asset"}


def build(profile) -> None:
    ocel, ground_truth = generate(profile)

    sqlite_path = OUT_DIR / f"{profile.name}.sqlite"
    json_path = OUT_DIR / f"{profile.name}.json"
    gt_path = OUT_DIR / f"{profile.name}.ground_truth.json"

    sqlite_io.write_sqlite(ocel, str(sqlite_path))
    json_io.write_json(ocel, str(json_path))
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    validate.validate_all(ocel, str(sqlite_path), required_object_types=REQUIRED_OBJECT_TYPES)

    print(f"wrote {sqlite_path}")
    print(f"wrote {json_path}")
    print(f"wrote {gt_path}")
    print(f"  objects={len(ocel.objects)} events={len(ocel.events)} ground_truth_entries={len(ground_truth)}")
    print("  Gate 0 validation: PASSED")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for profile in (MATURE_CSE_SCALED, SMALL_CSE_SCALED):
        print(f"building {profile.name} ...")
        build(profile)


if __name__ == "__main__":
    main()
