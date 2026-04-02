#!/bin/bash
# 本机运行：自动选择可用的 Python 环境
# 优先 conda py310 (有 GPU 支持) > .venv > python3.10 > python3
DIR="$(cd "$(dirname "$0")" && pwd)"
CONDA_PY="$HOME/.miniforge3/envs/py310/bin/python"
if [ -x "$CONDA_PY" ]; then
    exec "$CONDA_PY" "$DIR/buddy.py" "$@"
elif [ -x "$DIR/.venv/bin/python" ]; then
    exec "$DIR/.venv/bin/python" "$DIR/buddy.py" "$@"
elif command -v python3.10 &>/dev/null; then
    exec python3.10 "$DIR/buddy.py" "$@"
else
    exec python3 "$DIR/buddy.py" "$@"
fi
