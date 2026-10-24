#!/usr/bin/env python3
"""Prepare pinned public fixtures for kastellan#741 and audit them.

Fixture preparation downloads source text. The subsequent audit is offline.
Requires this project's installed CLI module and Python 3.11+; never installs
or imports the worker or its dependencies. Output directory must be new.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

CURRENT = "3f2ae1cfa985702f076e884fbf415272ea1a554e"
HISTORICAL = "ef8144f8ab5764782ba2691ce972b53af9d84928"
FILES = {
    "manifest": (CURRENT, "pyproject.toml", "ecf48cd426a33f486ec216a4c656b3f667257766da8630e837cd5fdd86b9e498"),
    "lock": (CURRENT, "uv.lock", "c4cf13dd05f0e4889e4d64c525a658e97b8a76ee2b0c7634cda3075c8d0cba71"),
    "historical-lock": (HISTORICAL, "uv.lock", "fc36de418441a522ef4bfbe57d137da15df434df139331736561cff4a802efaa"),
}


def anyio_block(text):
    matches = [block for block in re.split(r"(?=^\[\[package\]\])", text, flags=re.M)
               if re.search(r'^name = "anyio"$', block, re.M)]
    if len(matches) != 1:
        raise ValueError("Expected exactly one anyio package block")
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--uv", help="Optional native uv executable for comparison")
    args = parser.parse_args()
    args.output = args.output.absolute()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {}
    for label, (commit, filename, expected_hash) in FILES.items():
        url = f"https://raw.githubusercontent.com/hherb/kastellan/{commit}/workers/gliner-relex/{filename}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError(f"Source size/hash mismatch: {label}")
        sources[label] = data.decode("utf-8")
    original = sources["lock"]
    previous = anyio_block(sources["historical-lock"])
    if not re.search(r'^version = "4\.13\.0"$', previous, re.M):
        raise ValueError("Historical block is not anyio4.13.0")
    fixtures = [
        ("valid", original, 0),
        ("below-floor", original.replace(anyio_block(original), previous), 1),
        ("missing-anyio", original.replace(anyio_block(original), ""), 2),
    ]
    records = []
    for label, lock, expected in fixtures:
        directory = args.output / label
        directory.mkdir()
        (directory / "pyproject.toml").write_text(sources["manifest"])
        (directory / "uv.lock").write_text(lock)
        paths = [directory / "pyproject.toml", directory / "uv.lock"]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        commands = [("checker", [sys.executable, "-m", "uv_lock_integrity", str(directory), "--format", "json"])]
        if args.uv and label != "missing-anyio":
            commands.append(("native", [args.uv, "lock", "--check", "--offline", "--python", sys.executable]))
        for kind, argv in commands:
            result = subprocess.run(argv, cwd=directory, capture_output=True, text=True, timeout=60)
            records.append({"fixture": label, "kind": kind, "argv": argv, "exit": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
            if kind == "checker" and result.returncode != expected:
                raise ValueError(f"{label}: expected checker exit{expected}, got{result.returncode}")
        if before != [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]:
            raise ValueError(f"Input changed during checks: {label}")
    report = {"source_commit": CURRENT, "historical_block_commit": HISTORICAL,
              "scope": "Controlled mutation of public files, not an affected deployment or vulnerability audit.",
              "inputs_unchanged": True, "commands": records}
    (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"results": str(args.output / "results.json"),
                      "checker_exits": [row[2] for row in fixtures], "inputs_unchanged": True}))


if __name__ == "__main__":
    main()
