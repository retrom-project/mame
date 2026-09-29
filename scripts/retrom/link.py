"""Link identical MAME object code as static families and shared-runtime families."""
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from build_graph import archive, make_values, partition

EXPORTS = ["retrom_mame_abi", "retrom_mame_build_id", "retrom_mame_fps", "retrom_mame_sample_rate", "retrom_mame_axis", "retrom_mame_attach", "retrom_mame_driver_count", "retrom_mame_driver_name", "retrom_mame_start", "retrom_mame_step",
           "retrom_mame_listxml",
           "retrom_mame_aspect_ratio",
           "retrom_mame_key", "retrom_mame_button", "retrom_mame_width", "retrom_mame_height", "retrom_mame_frames", "retrom_mame_pixels",
           "retrom_mame_audio", "retrom_mame_audio_count", "retrom_mame_save_size", "retrom_mame_save", "retrom_mame_restore", "retrom_mame_peek", "retrom_mame_stop",
           "malloc", "free"]


def fingerprint(root, families):
    digest = hashlib.sha256()
    digest.update(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root))
    digest.update(subprocess.check_output(["git", "diff", "HEAD", "--", "src", "scripts/genie.lua", "scripts/src"], cwd=root))
    # Browser tests, documentation and packaging do not change the native ABI.
    for name in ("bridge.cpp", "family.h", "families.json", "build.py", "build_graph.py", "link.py", "wasm_metadata.py"):
        path = root / "scripts/retrom" / name
        digest.update(name.encode() + b"\0" + path.read_bytes())
    digest.update(json.dumps({name: family["sources"] for name, family in sorted(families.items())}, sort_keys=True).encode())
    return digest.hexdigest()


def link_all(root, build, output, project, projects, families, env):
    def run(argv, cwd=project):
        print("+", " ".join(map(str, argv))[:1400], flush=True)
        args = list(map(str, argv))
        destination = Path(args[args.index("-o") + 1]) if "-o" in args else None
        products, cache = [], None
        if destination and destination.suffix in (".wasm", ".mjs"):
            digest = hashlib.sha256(b"emscripten-3.1.74\0")
            for arg in args:
                if arg == str(destination):
                    digest.update(destination.name.encode() + b"\0")
                    continue
                digest.update(arg.encode() + b"\0")
                path = Path(arg.removeprefix("@"))
                if (arg.startswith("@") or path.suffix in (".a", ".o")) and path.is_file():
                    digest.update(path.read_bytes())
            products = [destination]
            if destination.suffix == ".mjs":
                products.append(destination.with_suffix(".wasm"))
            cache = build / "link-cache" / digest.hexdigest()
            try:
                record = json.loads((cache / "artifacts.json").read_text())
                valid = all(hashlib.sha256((cache / path.name).read_bytes()).hexdigest() == record[path.name]
                            for path in products)
            except (OSError, ValueError, KeyError):
                valid = False
            if valid:
                for path in products:
                    shutil.copyfile(cache / path.name, path)
                print("  reused verified link inputs:", destination.name, flush=True)
                return
        subprocess.run(args, cwd=cwd, env=env, check=True)
        if cache:
            cache.mkdir(parents=True, exist_ok=True)
            record = {}
            for path in products:
                shutil.copyfile(path, cache / path.name)
                record[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            pending = cache / "artifacts.json.tmp"
            pending.write_text(json.dumps(record))
            pending.replace(cache / "artifacts.json")

    main = make_values(project, "poc_all", env)
    objects = [path for path in main["OBJECTS"] if path.name != "drivlist.o"]
    run(["make", "-f", "poc_all.make", "config=libretro", "-j4",
         *[str(path.relative_to(root)).replace("build/", "../../../../", 1) for path in objects]])
    build_id = fingerprint(root, families)
    cpp = [Path(env["EMSCRIPTEN"]) / "em++", *main["FLAGS"], "-I" + str(root / "src/frontend/mame"),
           "-I" + str(root / "scripts/retrom"), '-DRETROM_POC_BUILD_ID="' + build_id + '"']
    bridge = build / "bridge.o"
    static_bridge = build / "bridge-static.o"
    run([*cpp, "-c", root / "scripts/retrom/bridge.cpp", "-o", bridge])
    run([*cpp, "-DRETROM_POC_STATIC", "-c", root / "scripts/retrom/bridge.cpp", "-o", static_bridge])
    common, specific = partition(project, projects, env)
    # GENie's header selector misses a few transitive device dependencies in
    # the broad legacy Arcade source set. Keep their implementations in the
    # shared runtime so every family that imports one resolves the same symbol.
    supplemental_sources = [
        "src/devices/machine/40105.cpp", "src/devices/machine/6525tpi.cpp",
        "src/devices/machine/ds1302.cpp", "src/devices/machine/ds75160a.cpp",
        "src/devices/machine/ds75161a.cpp", "src/devices/machine/mc6852.cpp",
        "src/devices/machine/at_keybc.cpp",
        "src/devices/machine/mos8726.cpp", "src/devices/machine/scc2698b.cpp",
        "src/devices/machine/vic_pl192.cpp", "src/devices/sound/t6721a.cpp",
        "src/devices/video/pc_vga_mediagx.cpp", "src/lib/formats/cbm_crt.cpp",
        "src/lib/formats/mfm_hd.cpp", "src/lib/formats/tibdd001_dsk.cpp",
    ]
    supplemental = []
    for source in (supplemental_sources if env.get("RETROM_MAME_ARCADE_PILOT") != "1" else []):
        obj = build / ("supplemental-" + source.replace("/", "-").replace(".cpp", ".o"))
        run([*cpp, "-c", root / source, "-o", obj])
        supplemental.append(obj)
    common_archives = archive(build / "common-devices.a", [*common, *supplemental], env)
    common_archives += [p for p in main["LIBDEPS"] if p.name not in
                        ("libmame_poc_all.a", "liboptional.a", "libformats.a", "libdasm.a")]
    driver_objects = make_values(project, "mame_poc_all", env)["OBJECTS"]
    linker = [Path(env["EMSCRIPTEN"]) / "em++", "-O2", "-fwasm-exceptions"]
    family_inputs = {}
    module_paths = {}
    for name, family in families.items():
        # MAME's own generated list contains all drivers belonging to these sources.
        directory = projects[name]
        generated = root / "build/generated/mame" / ("poc_" + name) / "drivlist.cpp"
        generated.parent.mkdir(parents=True, exist_ok=True)
        with generated.open("w") as handle:
            subprocess.run(["python3", root / "scripts/build/makedep.py", "-r", str(root), "driverlist",
                            str(root / "src/mame/mame.lst"), "-f", str(root / "build/generated/mame" / ("poc_" + name + ".flt"))],
                           cwd=root, check=True, stdout=handle)
        drivers = re.findall(r"GAME_EXTERN\((\w+)\);", generated.read_text())
        source = build / (name + "-family.cpp")
        source.write_text('#include "emu.h"\n#include "family.h"\n' +
                          "\n".join(f"GAME_EXTERN({d});" for d in drivers) +
                          "\nstatic game_driver const *const drivers[] = {" +
                          ",".join("&GAME_NAME(" + d + ")" for d in drivers) + "};\n" +
                          'extern "C" retrom_mame_family const *retrom_mame_family_v1() {\n' +
                          'static retrom_mame_family const family = {RETROM_POC_BUILD_ID, "' + name + '", ' +
                          str(len(drivers)) + ', drivers}; return &family; }\n')
        entry = build / (name + "-family.o")
        run([*cpp, "-c", source, "-o", entry])
        selected_drivers = make_values(directory, "mame_poc_" + name, env)["OBJECTS"]
        selected_names = {str(p).replace("mame_poc_" + name, "mame_poc_all") for p in selected_drivers}
        chosen = [p for p in driver_objects if str(p) in selected_names]
        if not chosen:
            raise RuntimeError("No driver objects selected: " + name)
        archives = archive(build / (name + "-devices.a"), specific[name], env)
        archives += archive(build / (name + "-drivers.a"), chosen, env)
        family_inputs[name] = [entry, *archives]
        module = output / ("mame-" + name + ".wasm")
        run([*linker, "-sSIDE_MODULE=2", '-sEXPORTED_FUNCTIONS=["_retrom_mame_family_v1"]',
             entry, *archives, "-o", module])
        module_paths[name] = module
        family["drivers"] = drivers
    # Keep exactly the shared definitions referenced by any side module. Do not
    # link the modules into the main command: that would create eager dependencies.
    from wasm_metadata import imports
    required = sorted({symbol for path in module_paths.values() for symbol in imports(path)
                       if symbol not in ("memory", "__indirect_function_table", "__memory_base", "__table_base")})
    retain = build / "retain.rsp"
    retain.write_text("\n".join("-Wl,--export-if-defined=" + symbol for symbol in required) + "\n")
    flags = ["--no-entry", "-sMODULARIZE=1", "-sEXPORT_ES6=1", "-sEXPORT_NAME=createMame", "-sENVIRONMENT=web,node",
             "-sALLOW_MEMORY_GROWTH=1", "-sINITIAL_MEMORY=67108864", "-sSTACK_SIZE=5242880",
             "-sFORCE_FILESYSTEM=1", "-sASSERTIONS=1", "-sEXPORTED_FUNCTIONS=" + json.dumps(["_" + x for x in EXPORTS]),
             '-sEXPORTED_RUNTIME_METHODS=["FS","ccall","UTF8ToString"]']
    run([*linker, *flags, "-sMAIN_MODULE=2", "-sEXPORTED_RUNTIME_METHODS=[FS,ccall,UTF8ToString,loadDynamicLibrary]",
         "@" + str(retain), bridge, *objects, *common_archives, "-o", output / "mame-common.mjs"])
    if env.get("RETROM_MAME_STATIC_COMPARISON") == "1":
        for name, inputs in family_inputs.items():
            run([*linker, *flags, static_bridge, *objects, *inputs, *common_archives,
                 "-o", output / ("mame-static-" + name + ".mjs")])
    from package import package
    package(root, output, families, build_id, common, specific, env["RETROM_MAME_COMPRESSION_NODE"])
