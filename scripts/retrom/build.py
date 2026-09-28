#!/usr/bin/env python3
"""Build the isolated MAME dynamic-linking experiment with a pinned SDK."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "retrom"


def run(argv, **kwargs):
    print("+", " ".join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), cwd=ROOT, check=True, **kwargs)


def toolchain():
    sdk = Path(os.environ["RETROM_EMSDK_ROOT"]).resolve()
    emscripten = sdk / "upstream" / "emscripten"
    version = (emscripten / "emscripten-version.txt").read_text().strip().strip('"')
    if version != "3.1.74":
        raise RuntimeError(f"Expected Emscripten 3.1.74, received {version}")
    node = sdk / "node/20.18.0_64bit/bin/node"
    if subprocess.check_output([node, "--version"]).decode().strip() != "v20.18.0":
        raise RuntimeError("Expected the Emscripten SDK's Node.js 20.18.0")
    env = dict(os.environ)
    env.update(EMSCRIPTEN=str(emscripten), RETROM_MAME_COMPRESSION_NODE=str(node), RETROM_DYLINK_POC="1",
               EM_CACHE=str(BUILD / "emscripten-cache"))
    env["PATH"] = str(emscripten) + ":" + env["PATH"]
    return env


def generate(name, sources, env):
    project = ROOT / "build" / "projects" / "retro" / f"mame{name}" / "gmake-asmjs"
    flags = ["SUBTARGET=" + name, "SOURCES=" + ",".join(sources), "OSD=retro",
             "CONFIG=libretro", "CC=emcc", "CXX=em++", "LD=em++", "AR=emar",
             "PTR64=0", "NOASM=1", "NOWERROR=1", "NO_OPENGL=1", "USE_QTDEBUG=0",
             "NO_USE_MIDI=1", "NO_USE_PORTAUDIO=1",
             "NO_USE_BGFX=1", "DONT_USE_NETWORK=1",
             "PRECOMPILE=0", "OPTIMIZE=2", "SYMBOLS=0", "REGENIE=1"]
    run(["make", "-j12", *flags, "generate", str(project.relative_to(ROOT) / "Makefile")], env=env)
    return project


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    env = toolchain()
    if not (ROOT / "3rdparty/genie/bin/linux/genie").is_file():
        host = ["make", "-C", ROOT / "3rdparty/genie/build/gmake.linux", "CC=gcc", "CXX=g++", "AR=ar"]
        run([*host, "clean"])
        run([*host, "-j4"])
    families = json.loads((ROOT / "scripts/retrom/families.json").read_text())
    projects = {name: generate("poc_" + name, family["sources"], env)
                for name, family in families.items()}
    union = sorted({source for family in families.values() for source in family["sources"]})
    project = generate("poc_all", union, env)
    # The final link is owned by link.py; upstream's executable link stays unused.
    libraries = sorted(path.stem for path in project.glob("*.make") if path.stem != "poc_all")
    run(["make", "-C", project, "config=libretro", "-j" + os.environ.get("RETROM_BUILD_JOBS", "12"),
         *libraries], env=env)
    from link import link_all
    with tempfile.TemporaryDirectory(prefix="poc-build.", dir=BUILD) as temporary:
        poc = Path(temporary)
        link_all(ROOT, BUILD, poc, project, projects, families, env)
        from product_package import product_package
        product_package(ROOT, poc, output, Path(env["EMSCRIPTEN"]))
        shutil.copytree(poc, BUILD / "poc-current", dirs_exist_ok=True)


if __name__ == "__main__":
    main()
