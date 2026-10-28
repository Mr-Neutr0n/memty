#!/usr/bin/env bash
set -euo pipefail

extras_arg="${1:-}"
allowed_extras=(crypto mongodb server mcp)
extras=()

if [[ -n "$extras_arg" ]]; then
  IFS=',' read -r -a requested_extras <<< "$extras_arg"
  for extra in "${requested_extras[@]}"; do
    extra="${extra//[[:space:]]/}"
    [[ -n "$extra" ]] || continue
    valid=false
    for allowed in "${allowed_extras[@]}"; do
      [[ "$extra" == "$allowed" ]] && valid=true
    done
    if [[ "$valid" != true ]]; then
      echo "Unknown extra '$extra'. Choose from: ${allowed_extras[*]}" >&2
      exit 2
    fi
    extras+=("$extra")
  done
fi

python_bin="${PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    python_bin="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    python_bin="$(command -v python)"
  else
    echo "Python 3.10+ is required. Install Python, then run this script again." >&2
    exit 1
  fi
fi

if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required." >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "Git is required to install the package from GitHub." >&2
  exit 1
fi

install_root="${NEXORAI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/nexorai}"
venv="$install_root/venv"
mkdir -p "$install_root"
"$python_bin" -m venv "$venv"
"$venv/bin/python" -m pip install --upgrade pip

package="nexorai-smart-auto"
if ((${#extras[@]})); then
  extras_csv="$(IFS=,; printf '%s' "${extras[*]}")"
  package+="[$extras_csv]"
fi
"$venv/bin/python" -m pip install --upgrade "$package @ git+https://github.com/RohanNK86/Open_AI_Bot.git@main"

echo "MemoryPort and SmartRouter installed in: $venv"
echo "Vault database default: $HOME/.nexorai/memory.sqlite3"
echo "CLI: $venv/bin/nexor-vault --help"

