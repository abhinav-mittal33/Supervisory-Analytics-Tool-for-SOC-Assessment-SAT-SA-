"""Build Order Step 2/3: generate the dev-scale CSE_ALPHA_MATURE_DEV dataset and write
it to data/dev/, alongside its ground-truth sidecar. Run after any generator change to
refresh the on-disk dataset Gate 0 (and later gates) validate against.
"""
import json
from pathlib import Path

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV
from satsa.ocel import json_io, sqlite_io, validate

OUT_DIR = Path(__file__).parent.parent / "data" / "dev"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ocel, ground_truth = generate(MATURE_CSE_DEV)

    sqlite_path = OUT_DIR / f"{MATURE_CSE_DEV.name}.sqlite"
    json_path = OUT_DIR / f"{MATURE_CSE_DEV.name}.json"
    gt_path = OUT_DIR / f"{MATURE_CSE_DEV.name}.ground_truth.json"

    sqlite_io.write_sqlite(ocel, str(sqlite_path))
    json_io.write_json(ocel, str(json_path))
    with open(gt_path, "w") as f:
        json.dump(ground_truth, f, indent=2)

    validate.validate_all(ocel, str(sqlite_path), required_object_types={"Alert", "Case", "Analyst", "Queue", "Asset"})

    print(f"wrote {sqlite_path}")
    print(f"wrote {json_path}")
    print(f"wrote {gt_path}")
    print(f"objects={len(ocel.objects)} events={len(ocel.events)} ground_truth_entries={len(ground_truth)}")
    print("Gate 0 validation: PASSED")


if __name__ == "__main__":
    main()
