#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_file="${YEYING_OPS_CONFIG:-${ANALYZER_CONFIG:-${HOME}/.yeying/skills/ops/config.json}}"
exec python3 "${script_dir}/ops_workflow.py" run --config "${config_file}" "$@"
