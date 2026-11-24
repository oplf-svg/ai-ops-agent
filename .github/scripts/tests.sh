#!/usr/bin/env bash
# The tests of the grader. They need nothing but Python, no network and no package.
set -euo pipefail

python3 --version
python3 -B -m unittest discover --start-directory tests --top-level-directory .
