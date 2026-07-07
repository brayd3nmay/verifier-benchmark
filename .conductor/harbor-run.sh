#!/usr/bin/env bash
# Run a Harbor task in one of three configs. Auto-loads .env so you never
# export GEMINI_API_KEY by hand.
#   ./scripts/harbor-run.sh oracle samples/my-task   # expect reward 1
#   ./scripts/harbor-run.sh nop    samples/my-task   # expect reward 0
#   ./scripts/harbor-run.sh model  samples/my-task   # one trial -> logs/ (loop yourself)
# Extra args pass through, e.g.  ... model samples/x -k 3
set -euo pipefail

mode=${1:?usage: harbor-run.sh <oracle|nop|model> <task-path> [extra harbor args]}
task=${2:?usage: harbor-run.sh <oracle|nop|model> <task-path> [extra harbor args]}
shift 2

root="$(cd "$(dirname "$0")/.." && pwd)"
# ponytail: source .env so the key lives in harbor's env; no per-run export
[ -f "$root/.env" ] && { set -a; . "$root/.env"; set +a; }

case "$mode" in
  oracle) exec harbor run -p "$task" -a oracle "$@" ;;
  nop)    exec harbor run -p "$task" -a nop "$@" ;;
  model)  exec harbor run -p "$task" -a terminus-2 -m gemini/gemini-3.5-flash -o logs "$@" ;;
  *) echo "unknown mode: $mode (want oracle|nop|model)" >&2; exit 2 ;;
esac
