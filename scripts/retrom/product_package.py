"""Publish the supported machines with their shared runtime and driver families."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ABI = "retrom-mame-dylink-v1"


def product_package(root, poc, output, emscripten):
    manifest = json.loads((poc / "manifest.json").read_text())
    entries = {}
    for name in ("mame-common.mjs", "mame-common.wasm", "mame-apple.wasm", "mame-acorn.wasm", "mame-vintage.wasm"):
        asset = manifest["assets"][name]
        for suffix in ("", ".br"):
            shutil.copyfile(poc / (asset["path"] + suffix), output / (name + suffix))
        entries[name] = {"sha256": asset["sha256"], "sizeBytes": asset["sizeBytes"]}
    metadata = {"schemaVersion": 1, "adapterAbi": ABI, "buildId": manifest["buildId"],
                "emscripten": manifest["emscripten"], "assets": entries,
                "families": {"apple": {"module": "mame-apple.wasm", "machines": ["apple2p"]},
                             "acorn": {"module": "mame-acorn.wasm", "machines": ["atom"]},
                             "vintage": {"module": "mame-vintage.wasm", "machines": ["pv1000"]}}}
    (output / "mame-build.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    tracked = subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root).split(b"\0")
    paths = sorted(set(Path(p.decode()) for p in tracked if p))
    source_hash = hashlib.sha256()
    licenses = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            continue
        data = path.read_bytes()
        source_hash.update(str(relative).encode() + b"\0" + hashlib.sha256(data).digest())
        if relative.name.upper().startswith(("LICENSE", "COPYING")) or relative.parts[:2] == ("docs", "legal"):
            licenses.append(f"\n===== {relative} =====\n" + data.decode("utf-8", errors="replace"))
    if not licenses:
        raise RuntimeError("MAME license texts missing")
    licenses.append("\n===== Emscripten 3.1.74 LICENSE =====\n" + (emscripten / "LICENSE").read_text())
    (output / "LICENSES.txt").write_text("MAME and bundled third-party license texts\n" + "".join(licenses))
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root).decode().strip()
    files = [{"filename": p.name, "sizeBytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.iterdir())]
    descriptor = {"schemaVersion": 1, "kind": "RETROM_CORE_CANDIDATE_V1", "coreId": "mame",
                  "repository": "https://github.com/retrom-project/mame",
                  "branch": git("branch", "--show-current"), "commit": git("rev-parse", "HEAD"),
                  "dirty": bool(git("status", "--porcelain")), "sourceTreeSha256": source_hash.hexdigest(),
                  "adapterAbi": ABI, "files": files}
    (output / "retrom-core-candidate.json").write_text(json.dumps(descriptor, sort_keys=True, indent=2) + "\n")
