#!/usr/bin/env bash
# Puts one mistake at a time into a copy of the grader, and looks whether the tests notice it. "1/2" is the first of two parts.
set -euo pipefail

JOBS=${JOBS:-$(nproc 2>/dev/null || echo 1)} python3 -B -m tests.wrong "$@"
