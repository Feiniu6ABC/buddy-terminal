#!/bin/bash
# 本机运行：自动选择可用的 Python 环境
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -x "$DIR/.venv/bin/python" ]; then
    exec "$DIR/.venv/bin/python" "$DIR/buddy.py" "$@"
elif command -v python3.10 &>/dev/null; then
    exec python3.10 "$DIR/buddy.py" "$@"
else
    exec python3 "$DIR/buddy.py" "$@"
fi
