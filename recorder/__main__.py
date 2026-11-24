"""Makes recordings.

    python -m recorder sample      each cause once
    python -m recorder 2/4         the second of four parts of all of them
    python -m recorder CODE...     these causes once
"""

import collections
import concurrent.futures
import json
import os
import pathlib
import random
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

from grader import Broken
from recorder import build
from recorder.causes import CAUSES
from recorder.plan import chosen
from recorder.scene import Scene
from recorder.write import write
from world import IMAGE

OUT = build.BUILD / "recordings"
TRIES, JOBS = 3, int(os.environ.get("JOBS") or 3)


def digest(recording):
    """What is in it, in one line, for whoever reads the log of a run."""
    found = collections.Counter()
    for entry in recording.entries:
        match entry.source:
            case "log":
                found["log " + "/".join(entry.get(field) for field in ("what", "state", "reason", "error") if entry.get(field))] += 1
            case "front":
                found[f"front {entry.get('status')}"] += 1
            case "row":
                found["row " + "/".join(entry.get(field) for field in ("table", "state") if entry.get(field))] += 1
            case "process":
                found[f"{entry.get('kind')} {entry.get('exit')}"] += 1
            case "series" if entry.get("name") == "database_answers":
                found[f"answers {entry.get('value')}"] += 1
    for source, _, _ in recording.missing:
        found[f"gap in {source}"] += 1
    return ", ".join(f"{what} {number}" for what, number in sorted(found.items()))


def record(code, seed, version, commit):
    """One recording. What did not happen as it should is tried again, and the reason is kept."""
    cause, why = CAUSES[code], []
    for attempt in range(1, TRIES + 1):
        began = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="scene-") as folder:
            scene = Scene(folder, version, f"{code} {seed} {attempt}", cause.net)
            id = f"r{secrets.token_hex(6)}"
            try:
                scene.begin()
                cause.play(scene)
                noted, missing = scene.close()
                # Nothing in the handles depends on the cause.
                meta, recording = write(OUT / id, noted, random.Random(secrets.randbits(64)), commit, os.environ.get("GITHUB_SHA", "here"), seed, [id, *(program.name for program in scene.programs)], list(CAUSES), missing)
                sources = collections.Counter(entry.source for entry in recording.entries)
                return {
                    "id": id, "cause": code, "pair": cause.pair, "seed": seed, "meta": meta, "seconds": round(recording.entries[-1].at / 1000), "took": round(time.monotonic() - began), "tries": why,
                    "entries": dict(sorted(sources.items())), "facts": list(scene.facts), "digest": digest(recording)}
            except Exception as problem:
                shutil.rmtree(OUT / id, ignore_errors=True)
                last = [line for program in scene.programs for line in scene.last_lines(program)]
                why.append(f"{type(problem).__name__}: {str(problem)[:300]}")
                print(f"{code} {seed}, try {attempt}: {why[-1]}", *last, sep="\n    ", flush=True)
                if not isinstance(problem, (Broken, AssertionError)):
                    traceback.print_exc()
            finally:
                scene.finish()
    return {"cause": code, "pair": cause.pair, "seed": seed, "tries": why}


def main(words):
    todo = chosen(words)
    commit = build.commit()
    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir(parents=True)
    subprocess.run(["docker", "pull", "--quiet", IMAGE], check=True, stdout=subprocess.DEVNULL)
    versions = build.Versions()
    started = time.monotonic()
    # First what is right, and one after the other.
    made = {mistake: versions.get(mistake) for mistake in sorted({CAUSES[code].mistake for code, _ in todo}, key=lambda mistake: mistake or "")}
    print(f"{len(made)} versions built in {time.monotonic() - started:.0f} s.", flush=True)

    def one(task):
        code, seed = task
        done = record(code, seed, made[CAUSES[code].mistake], commit)
        if "id" in done:
            print(f"{code} {seed}: {done['seconds']} s, {sum(done['entries'].values())} entries, took {done['took']} s, {len(done['tries'])} tries in vain\n    {done['digest']}", flush=True)
        else:
            print(f"{code} {seed}: NOT RECORDED", flush=True)
        return done

    with concurrent.futures.ThreadPoolExecutor(JOBS) as pool:
        found = list(pool.map(one, todo))
    (OUT / "index.json").write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    missing = [done for done in found if "id" not in done]
    text = f"{len(found) - len(missing)} of {len(found)} recordings, {sum(len(done['tries']) for done in found)} tries in vain, {time.monotonic() - started:.0f} s."
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        rows = "".join(f"| {done['cause']} | {done['seed']} | {done.get('seconds', '**none**')} | {sum(done.get('entries', {}).values())} | {'; '.join(done['tries']).replace('|', '/')[:120]} |\n" for done in found)
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"### {text}\n\n| Cause | Seed | Seconds | Entries | Tries in vain |\n|---|---|---|---|---|\n{rows}\n")
    return 1 if missing else 0


if __name__ == "__main__":
    pathlib.Path(build.BUILD).mkdir(exist_ok=True)
    sys.exit(main(sys.argv[1:]))
