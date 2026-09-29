"""Publish immutable local PoC assets and a measurement manifest, never a Release."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def package(root, output, families, build_id, common, specific, node):
    assets = {}
    for path in sorted(output.iterdir()):
        if path.suffix not in (".wasm", ".mjs"):
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        name = path.stem + "." + digest[:20] + path.suffix
        path.rename(output / name)
        assets[path.name] = {"path": name, "sha256": digest, "sizeBytes": len(data)}
    subprocess.run([node, str(root / "scripts/retrom/compress.mjs"), str(output), str(root / "build/retrom/poc-current")], check=True)
    for asset in assets.values():
        asset["gzipBytes"] = (output / (asset["path"] + ".gz")).stat().st_size
        asset["brotliBytes"] = (output / (asset["path"] + ".br")).stat().st_size
    manifest = {"schemaVersion": 1, "experimental": True, "buildId": build_id,
                "emscripten": "3.1.74", "assets": assets, "families": families,
                "commonDeviceObjects": len(common),
                "familyDeviceObjects": {name: len(objects) for name, objects in specific.items()}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "object-partition.json").write_text(json.dumps({
        "common": [str(Path(p).relative_to(root)) for p in common],
        "families": {k: [str(Path(p).relative_to(root)) for p in v] for k, v in specific.items()}
    }, indent=2) + "\n")
    for path in (root / "scripts/retrom/web").iterdir():
        shutil.copyfile(path, output / path.name)
    subprocess.run(["python3", str(root / "scripts/retrom/diagnostics.py"), str(output / "diagnostics")], check=True)
    descriptor = {"schemaVersion": 1, "coreId": "mame", "experimental": True,
                  "adapterAbi": "retrom-mame-dylink-poc-v1", "buildId": build_id,
                  "artifacts": assets}
    (output / "retrom-core-candidate.json").write_text(json.dumps(descriptor, indent=2) + "\n")
