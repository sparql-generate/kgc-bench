"""The RML engines added on 2026-11-26 (RocketRML, FlexRML, BURP, RMLStreamer)
and ShExML, an engine with a mapping language of its own:
where each one is installed (scripts/fetch_engines.sh, pins of versions.env)
and the command that runs it. Shared by the conformance harness
(harness.conformance, mode rml) and the performance harness (harness.engines).

Each engine runs as its documentation shows, with its default options, except:

- RocketRML has no command line: scripts/rocketrml/rocketrml.js calls its
  parseFile with N-Quads output (toRDF), on the pinned Node.js 20 (its jsonld 5
  does not load on Node.js 22);
- RMLStreamer runs standalone (an embedded local Flink, no cluster), on JDK 11
  (Flink 1.14 does not run on JDK 21), and writes one part file per parallel task
  into a directory: merge_parts() concatenates them, untimed;
- BURP reads only the RML of the W3C KG-Construct CG (http://w3id.org/rml/): in
  the performance runs, the legacy GTFS mapping is converted to it
  (harness.workloads.to_rml_core), untimed.

``heap`` is the maximum heap given to the Java and Node.js engines in the
performance runs (75 % of the memory limit, as every Java engine); the
conformance runs give none (each runtime's default, as for the other engines).
"""

import os
import re
import shutil

from harness import ENGINES, ROOT, VERSIONS, java

NEW_RML_ENGINES = ("rocketrml", "flexrml", "burp", "rmlstreamer")


def node():
    return os.path.join(ENGINES, "node-v%s-linux-x64" % VERSIONS["NODE_VERSION"], "bin", "node")


def path(engine):
    """The installed artefact of an engine."""
    v = VERSIONS
    return {
        "rocketrml": os.path.join(ENGINES, "rocketrml-%s" % v["ROCKETRML_VERSION"], "node_modules",
                                  "rocketrml"),
        "flexrml": os.path.join(ENGINES, "flexrml-%s" % v["FLEXRML_VERSION"]),
        "burp": os.path.join(ENGINES, "burp-%s.jar" % v["BURP_VERSION"]),
        "rmlstreamer": os.path.join(ENGINES, "RMLStreamer-%s-standalone.jar" % v["RMLSTREAMER_VERSION"]),
        "shexml": os.path.join(ENGINES, "ShExML-%s.jar" % v["SHEXML_VERSION"]),
    }.get(engine, "")


def available(engine):
    if engine == "rocketrml" and not os.path.exists(node()):
        return False
    return os.path.exists(path(engine))


def version(engine):
    key = {"rocketrml": "ROCKETRML_VERSION", "flexrml": "FLEXRML_VERSION", "burp": "BURP_VERSION",
           "rmlstreamer": "RMLSTREAMER_VERSION", "shexml": "SHEXML_VERSION"}[engine]
    return VERSIONS.get(key, "")


LABEL = {"rocketrml": "RocketRML", "flexrml": "FlexRML", "burp": "BURP",
         "rmlstreamer": "RMLStreamer", "shexml": "ShExML"}


def java_rmlstreamer():
    return java("JAVA_HOME_RMLSTREAMER")


def node_heap(heap):
    """--max-old-space-size (MB) for a Java-style heap size (12g, 12288m)."""
    m = re.match(r"^(\d+)([kmgKMG]?)$", heap or "")
    if not m:
        return []
    n = int(m.group(1)) * {"k": 1 / 1024, "m": 1, "g": 1024, "": 1 / 2**20}[m.group(2).lower()]
    return ["--max-old-space-size=%d" % n]


def command(engine, mapping, output, base=None, heap=None):
    """The command that runs an RML engine on a mapping, writing output (for
    RMLStreamer: a directory of part files, see merge_parts)."""
    xmx = ["-Xmx" + heap] if heap else []
    if engine == "rocketrml":
        return [node()] + node_heap(heap) + [os.path.join(ROOT, "scripts", "rocketrml", "rocketrml.js"),
                                             path("rocketrml"), mapping, output]
    if engine == "flexrml":
        return [path("flexrml"), "-m", mapping, "-o", output] + (["-b", base] if base else [])
    if engine == "burp":
        return [java()] + xmx + ["-jar", path("burp"), "-m", mapping, "-o", output] + (
            ["-b", base] if base else [])
    if engine == "rmlstreamer":
        return [java_rmlstreamer()] + xmx + ["-jar", path("rmlstreamer"), "toFile", "-m", mapping,
                                             "-o", output] + (["-i", base] if base else [])
    raise ValueError("unknown engine %s" % engine)


def merge_parts(parts, output):
    """Concatenate the part files that RMLStreamer wrote into the directory
    parts, into output, deleting each part once copied (at GTFS scale 1000 the
    output is tens of GB). Returns output, or None when there is no part."""
    if not os.path.isdir(parts):
        return output if os.path.exists(output) else None
    files = []
    for d, _, fs in os.walk(parts):
        files += [os.path.join(d, f) for f in fs if not f.startswith(".")]
    with open(output, "wb") as out:
        for f in sorted(files):
            with open(f, "rb") as src:
                shutil.copyfileobj(src, out, 1 << 22)
            os.remove(f)
    shutil.rmtree(parts, ignore_errors=True)
    return output
