#!/usr/bin/env bash
# The tests of the grader and of the recorder. They need nothing but Python, no network and no package.
set -euo pipefail
cd "$(dirname "$0")/../.."

python3 --version
python3 -B -m unittest discover --start-directory tests --top-level-directory .

# A branch that must not be merged yet has this file: one line that says why, and until when. It comes last, so that everything
# else is seen. A link is not followed, because the log is public.
if [ -f HOLD ] && [ ! -L HOLD ]; then
  echo "Not to be merged yet: $(head -n 1 HOLD)"
  exit 1
elif [ -e HOLD ] || [ -L HOLD ]; then
  echo "Not to be merged yet: HOLD is not a plain file."
  exit 1
fi
