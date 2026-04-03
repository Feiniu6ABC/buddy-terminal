#!/bin/bash
# Buddy Pet launcher - 自动选择可用的 Python 环境
DIR="$(cd "$(dirname "$0")" && pwd)"

# 内网环境: 尝试 module load python 3.10
if command -v module &>/dev/null; then
    module load python/3.10.17 2>/dev/null || module load python/3.10 2>/dev/null || true
fi

# 按优先级查找 Python: conda py310 > .venv > python3.10 > python3
find_python() {
    # conda (GPU 支持)
    local conda="$HOME/.miniforge3/envs/py310/bin/python"
    [ -x "$conda" ] && echo "$conda" && return
    # 项目 .venv
    [ -x "$DIR/.venv/bin/python" ] && echo "$DIR/.venv/bin/python" && return
    # 系统 python3.10
    command -v python3.10 &>/dev/null && echo "python3.10" && return
    # 任意 python3
    echo "python3"
}

exec "$(find_python)" "$DIR/buddy.py" "$@"
