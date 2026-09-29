"""Build a compact, deterministic core Release from a verified PFB candidate."""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ARCHIVE = "mame-current-assets.zip"
METADATA = "rpg-runtime-release.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build_archive(root, candidate_dir, output_dir, tag):
    commit = subprocess.check_output(["git", "rev-parse", f"{tag}^{{commit}}"], cwd=root, text=True).strip()
    descriptor = json.loads((candidate_dir / "retrom-core-candidate.json").read_text())
    if (descriptor.get("kind") != "RETROM_CORE_CANDIDATE_V1" or descriptor.get("coreId") != "mame" or
            descriptor.get("repository") != "https://github.com/retrom-project/mame" or
            descriptor.get("adapterAbi") != "retrom-mame-dylink-v1" or descriptor.get("dirty") or
            not re.fullmatch(r"retrom-core-gf65d5ba9bc42-r[1-9][0-9]*", tag)):
        raise ValueError("invalid MAME candidate or release tag")
    files = descriptor["files"]
    names = [entry["filename"] for entry in files]
    if len(files) < 3 or names != sorted(set(names)) or any(not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name.endswith(".br") for name in names):
        raise ValueError("invalid candidate file list")
    if {p.name for p in candidate_dir.iterdir() if p.is_file()} != set(names) | {"retrom-core-candidate.json"}:
        raise ValueError("candidate files changed")
    verified = {}
    for entry in files:
        name = entry["filename"]
        path = candidate_dir / name
        if path.is_symlink():
            raise ValueError(f"candidate symlink: {name}")
        data = path.read_bytes()
        if len(data) != entry["sizeBytes"] or digest(data) != entry["sha256"]:
            raise ValueError(f"candidate hash mismatch: {name}")
        verified[name] = data
    raw_names = names
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / ARCHIVE
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
        for name in raw_names:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, verified[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    metadata = {"schemaVersion": 1, "repository": descriptor["repository"], "tag": tag,
                "commit": commit, "adapterAbi": descriptor["adapterAbi"],
                "archive": {"filename": ARCHIVE, "sizeBytes": archive_path.stat().st_size,
                            "sha256": digest(archive_path.read_bytes()), "format": "zip",
                            "files": raw_names},
                "files": files}
    (output_dir / METADATA).write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("tag")
    args = parser.parse_args()
    print(json.dumps(build_archive(Path(__file__).resolve().parents[2], args.candidate_dir, args.output_dir, args.tag)["archive"]))
