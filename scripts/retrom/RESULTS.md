# MAME dynamic-linking PoC result

Measured on 2026-09-28 in the isolated `mame-dylink-poc` workspace, against
upstream fork commit `f65d5ba9bc42febea7cd76d4559827d0e1271581` plus this
experimental patch. Native build ID:
`52b3ed7e6df21abd858273c249cee806324badee1dbfc42da108d2e215cd42a1`.

The experiment supports the proposed download-sharing direction: with Brotli,
all three representative families together use **50.58% fewer transferred code
bytes**. Every two-family combination also saves bytes. First use of any single
family costs more. This snapshot predates the Apple II+ product pilot described in README.md;
its measurements and acceptance claims apply only to this native build ID.

## Payload measurements

MiB means 1,048,576 bytes. These totals include WASM and generated Emscripten JS,
excluding the shared PoC HTML/loader and diagnostic firmware. Both controls use
the same PIC objects, `-O2`, native WASM exceptions and assertions, without LTO.
They are controlled experimental baselines, not optimized production builds.

| Launches within one build version | Static, Brotli MiB | Dynamic, Brotli MiB | Reduction |
| --- | ---: | ---: | ---: |
| Apple II family only | 3.899 | 4.393 | -12.67% |
| Atom family only | 3.197 | 4.147 | -29.69% |
| PV-1000 only | 2.275 | 3.929 | -72.70% |
| Apple II + Atom | 7.096 | 4.621 | 34.88% |
| Apple II + PV-1000 | 6.173 | 4.403 | 28.68% |
| Atom + PV-1000 | 5.472 | 4.157 | 24.03% |
| All three | 9.371 | 4.631 | 50.58% |

The shared code payload is 4,108,652 Brotli bytes: 4,033,711 bytes of common WASM
plus 74,941 bytes of generated JS. Once cached, additional family WASM costs:

| Family | Additional Brotli bytes | Included real driver names | Optional device objects |
| --- | ---: | ---: | ---: |
| Apple II | 497,325 | 23 | 475 |
| Acorn Atom | 239,382 | 5 | 222 |
| Casio PV-1000 | 10,952 | 1 | 1 |

The common partition contains 436 optional device/format/disassembler objects,
in addition to MAME's framework, frontend and support libraries. Device graphs
overlap, so per-family object counts are not additive. The internal empty driver
is omitted from the driver-name counts above.

With gzip, the three-family total falls from 15.732 to 8.200 MiB (47.87%).
Without HTTP compression, it **increases** from 106.276 to 112.530 MiB (5.88%).
The common WASM alone is 110,895,053 uncompressed bytes; Brotli/gzip delivery is
therefore a required deployment consideration, and decompression/compilation
cost cannot be inferred from transferred bytes alone.

## Browser evidence

Chrome for Testing 149.0.7827.55 on Linux x86-64 passed all six combinations:
Apple II+, Atom and PV-1000, each with static and dynamic linking. For each case,
the test executed original diagnostic firmware on the real MAME driver and
verified:

- Rendering and non-silent PCM output.
- Browser keyboard input changing guest RAM and rendered pixels.
- A saved state restored into a newly created instance after first changing
  that instance's state; input still works after restoration.
- Rejection of a second family registration in the same instance.

The Apple, Atom and PV-1000 state payloads were 456,572, 435,308 and 76,746 bytes
respectively, identical between link modes. Observed WASM linear memory was
76.81 MiB for Apple/Atom and 64 MiB for PV-1000 in both modes. This does not measure
total browser memory, compiled code, download buffers or peak decompression use.

The A → B → A sequence reused CacheStorage bytes. Server-side request evidence
recorded the common WASM **exactly once** across family changes and fresh
instances before deliberate fault injection. Its single response used Brotli
and transferred 4,033,711 bytes. Common generated JS also transferred once.

Negative checks passed for an unknown family, an expected-build mismatch,
native rejection of a valid WASM module with a different descriptor build ID,
corrupt cached bytes, and unavailable CacheStorage. Fault injection runs after
the one-transfer assertion and may add requests.

Local raw evidence is generated at `build/retrom/evidence/results.json`, with
twelve screenshots beside it; complete byte comparisons are at
`build/retrom/measurements.json`. Startup and 120-step timings are recorded per
case there. They are single desktop observations with different cache states,
not a statistical benchmark or a mobile performance claim.

## Validation and remaining scope

The explicit PFB core build passed. Device-partition unit tests passed (3),
Retrom's `workspace-check` passed including catalog tests (6), and selected
workspace checkout/origin checks passed. Python compilation, JavaScript syntax
checks and Git whitespace checks passed. A later build reused all seven linked
outputs after verifying input hashes and cached output hashes; cached compressed
bytes are decoded and compared before reuse.

The full Retrom product suite was not run: no Player, Runtime Provider, Target,
API or database behavior changed. Other browsers, mobile devices, threads,
commercial games, vendor firmware and the other included driver variants have
not been accepted by this experiment. No production release, PR or merge is
part of this result.

The cache guarantee is for matching artifacts from this native build. The C++
boundary is tightly coupled to MAME and Emscripten; new family imports or source
changes can require rebuilding the common module and refreshing its cache.
Each launch creates fresh memory and loads one family. Reusing downloaded bytes
does not imply reusing a live machine or unloading families safely.

At the time of this snapshot, the next product step was to represent common/family dependencies in the Runtime
asset contract, then validate real content and checkpoints through Retrom. Before
expanding the driver inventory, continue measuring each family's dependency
graph and first-use cost; this three-family result does not establish that one
universal common module is best for every MAME driver.
