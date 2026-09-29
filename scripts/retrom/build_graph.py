"""Read GENie's selected object graph without maintaining a parallel device list."""
from collections import Counter
from pathlib import Path
import shlex
import subprocess


def make_values(project, name, env):
    variables = ("OBJECTS", "TARGET", "ALL_CXXFLAGS", "FORCE_INCLUDE", "LIBDEPS")
    recipe = "retrom-values:;@" + "".join(f"$(info RETROM_{key}=$({key}))" for key in variables) + ":"
    result = subprocess.run(["make", "--no-print-directory", "-s", "-f", name + ".make",
                             "config=libretro", "--eval=" + recipe, "retrom-values"],
                            cwd=project, env=env, check=True, text=True, capture_output=True)
    values = dict(line.removeprefix("RETROM_").split("=", 1)
                  for line in result.stdout.splitlines() if line.startswith("RETROM_"))
    for key in ("OBJECTS", "LIBDEPS"):
        values[key] = [(project / path).resolve() for path in shlex.split(values[key])]
    values["TARGET"] = (project / values["TARGET"]).resolve()
    values["FLAGS"] = shlex.split(values["ALL_CXXFLAGS"] + " " + values["FORCE_INCLUDE"])
    return values


def partition(project, projects, env):
    selected = {}
    for name, directory in projects.items():
        objects = [p for library in ("optional", "formats", "dasm")
                   for p in make_values(directory, library, env)["OBJECTS"]]
        selected[name] = {str(path).replace("mame_poc_" + name, "mame_poc_all") for path in objects}
    occurrences = Counter(path for paths in selected.values() for path in paths)
    common = {path for path, count in occurrences.items() if count > 1}
    all_objects = {str(path) for library in ("optional", "formats", "dasm")
                   for path in make_values(project, library, env)["OBJECTS"]}
    missing = set(occurrences) - all_objects
    if missing:
        raise RuntimeError(f"Family objects absent from union build: {sorted(missing)}")
    # Sharing an object is only valid if it does not depend back on a private
    # family object. Compute the closed subset; duplicate other shared objects
    # in each family instead of inflating the common module with their closure.
    definitions, undefined = symbols(all_objects, env)
    common = closed_common(common, definitions, undefined)
    print(f"Closed shared device graph: {len(common)} of {len(all_objects)} objects", flush=True)
    return sorted(common), {name: sorted(paths - common) for name, paths in selected.items()}


def closed_common(candidates, definitions, undefined):
    common = set(candidates)
    while True:
        remove = {path for path in common if any(
            symbol in definitions and not definitions[symbol].intersection(common)
            for symbol in undefined.get(path, set()))}
        if not remove:
            return common
        common -= remove


def symbols(objects, env):
    llvm = Path(env["EMSCRIPTEN"]).parent / "bin" / "llvm-nm"
    result = subprocess.run([str(llvm), "-P", "-A", "--extern-only", *sorted(objects)],
                            env=env, text=True, capture_output=True, check=True)
    definitions, undefined = {}, {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 3:
            continue
        path, symbol, kind = fields[0].removesuffix(":"), fields[1], fields[2]
        if kind in ("U", "w", "v"):
            undefined.setdefault(path, set()).add(symbol)
        else:
            definitions.setdefault(symbol, set()).add(path)
    return definitions, undefined


def archive(path, objects, env):
    # Replace only the generated archive, so removed objects cannot remain members.
    path.unlink(missing_ok=True)
    if objects:
        subprocess.run([str(Path(env["EMSCRIPTEN"]) / "emar"), "rcs", str(path), *map(str, objects)],
                       env=env, check=True)
        return [path]
    return []
