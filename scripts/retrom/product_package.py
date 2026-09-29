"""Publish the supported machines with their shared runtime and driver families."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ABI = "retrom-mame-dylink-v1"


def product_package(root, poc, output, emscripten):
    if not (poc / "mame-arcade.xml").is_file():
        node = emscripten.parents[1] / "node/20.18.0_64bit/bin/node"
        subprocess.run(["python3", root / "scripts/retrom/generate_arcade_dat.py", poc, node], check=True)
    manifest = json.loads((poc / "manifest.json").read_text())
    entries = {}
    family_names = sorted(manifest["families"])
    module_names = ("mame-common.mjs", "mame-common.wasm", *(f"mame-{family}.wasm" for family in family_names))
    for name in module_names:
        asset = manifest["assets"][name]
        shutil.copyfile(poc / asset["path"], output / name)
        entries[name] = {"sha256": asset["sha256"], "sizeBytes": asset["sizeBytes"]}
    metadata = {"schemaVersion": 1, "adapterAbi": ABI, "buildId": manifest["buildId"],
                "emscripten": manifest["emscripten"], "assets": entries,
                "families": {name: {"module": f"mame-{name}.wasm", "machines": family["drivers"],
                                    "arcade": family.get("arcade", False)}
                             for name, family in sorted(manifest["families"].items())}}
    (output / "mame-build.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    shutil.copyfile(poc / "mame-arcade.xml", output / "mame-arcade.xml")
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
    release_names = ("LICENSES.txt", "mame-arcade.xml", "mame-build.json",
                     *module_names)
    files = [{"filename": name, "sizeBytes": (output / name).stat().st_size,
              "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in sorted(release_names)]
    descriptor = {"schemaVersion": 1, "kind": "RETROM_CORE_CANDIDATE_V1", "coreId": "mame",
                  "repository": "https://github.com/retrom-project/mame",
                  "branch": git("branch", "--show-current"), "commit": git("rev-parse", "HEAD"),
                  "dirty": bool(git("status", "--porcelain")), "sourceTreeSha256": source_hash.hexdigest(),
                  "adapterAbi": ABI, "files": files}
    (output / "retrom-core-candidate.json").write_text(json.dumps(descriptor, sort_keys=True, indent=2) + "\n")
