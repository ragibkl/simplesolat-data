#!/usr/bin/env python3
"""
Build a dated zone mapping from an existing one with some shapes moved to
other zones (e.g. Malaysia from 2027-01-01: Selangor's districts to MFSGR).

The source file (sources/remaps/*.yaml) names the base mapping, the output
and the shapes to move. Every moved shape must exist in the base, and every
target zone must exist in data/zones/{CC}.yaml with the same state.

Usage: python3 scripts/build_remap.py sources/remaps/MY-20270101.yaml
"""

import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(path):
    with open(path) as f:
        spec = yaml.safe_load(f)
    with open(os.path.join(ROOT, "data", spec["base"])) as f:
        mapping = json.load(f)
    cc = os.path.basename(spec["out"]).split("-")[0]
    with open(os.path.join(ROOT, "data", "zones", f"{cc}.yaml")) as f:
        zones = {z["code"]: z for z in yaml.safe_load(f)["zones"]}

    for shape, zone in spec["set"].items():
        if shape not in mapping:
            sys.exit(f"{shape}: not in {spec['base']}")
        if zone not in zones:
            sys.exit(f"{zone}: not in zones/{cc}.yaml")
        if zones[zone]["state"] != mapping[shape]["state"]:
            sys.exit(f"{shape}: state {mapping[shape]['state']} but {zone} is in {zones[zone]['state']}")
        print(f"  {shape}: {mapping[shape]['zone']} -> {zone}")
        mapping[shape] = {**mapping[shape], "zone": zone}

    out = os.path.join(ROOT, "data", spec["out"])
    if os.path.exists(out):
        with open(out) as f:
            if json.load(f) != mapping:
                sys.exit(f"{spec['out']} exists with different content: dated files are never edited")
        print(f"{spec['out']}: unchanged")
        return
    with open(out, "w") as f:
        # Same layout as generate_mappings.py writes (indent 1, no final newline).
        json.dump(mapping, f, indent=1, ensure_ascii=False)
    print(f"wrote {spec['out']}")


if __name__ == "__main__":
    main(sys.argv[1])
