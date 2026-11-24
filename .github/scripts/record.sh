#!/usr/bin/env bash
# Makes the recordings of webhook-platform. "sample" is each cause once, "1/4" the first of four parts of all of them.
# Needs Docker, .NET and webhook-platform beside it, at the commit that stands in webhook-platform.commit.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ ! -d webhook-platform ]; then
  echo "webhook-platform is not here."
  exit 1
fi
bash webhook-platform/.github/scripts/prepare.sh
webhook-platform/build/venv/bin/python -B -m recorder "$@"
