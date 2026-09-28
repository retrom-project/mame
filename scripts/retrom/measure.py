#!/usr/bin/env python3
"""Report complete launch payloads, including the JS host, from built bytes."""
import itertools
import json
from pathlib import Path
import sys


def measure(root):
    manifest = json.loads((root / "manifest.json").read_text())
    assets, families = manifest["assets"], list(manifest["families"])
    result = {"buildId": manifest["buildId"], "units": "bytes", "encodings": {}}
    for encoding in ("sizeBytes", "gzipBytes", "brotliBytes"):
        common = sum(assets["mame-common." + ext][encoding] for ext in ("wasm", "mjs"))
        side = {f: assets[f"mame-{f}.wasm"][encoding] for f in families}
        static = {f: sum(assets[f"mame-static-{f}.{ext}"][encoding] for ext in ("wasm", "mjs")) for f in families}
        combinations = []
        for length in range(1, len(families) + 1):
            for selected in itertools.combinations(families, length):
                dynamic = common + sum(side[f] for f in selected)
                baseline = sum(static[f] for f in selected)
                combinations.append({"families": selected, "static": baseline, "dynamic": dynamic,
                                     "savedBytes": baseline - dynamic,
                                     "savedPercent": round(100 * (baseline - dynamic) / baseline, 2)})
        result["encodings"][encoding] = {"common": common, "additionalFamily": side,
                                         "staticFamily": static, "combinations": combinations}
    return result


if __name__ == "__main__":
    print(json.dumps(measure(Path(sys.argv[1])), indent=2))
