"""配置持久化 + tmux dock/undock"""

import json
import os

from .constants import CONFIG_PATH, DIM, RST


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _entry_script():
    """返回 buddy.py 入口脚本的绝对路径"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "buddy.py")


def dock_companion():
    import shutil, subprocess
    if not shutil.which("tmux"):
        print("  需要安装 tmux: sudo apt install tmux")
        return
    config = load_config()
    if not config.get("companion"):
        print("\n  你还没有伙伴！先用 'hatch' 孵化一个。\n")
        return

    script = _entry_script()
    runsh = os.path.join(os.path.dirname(script), "run.sh")
    launcher = f"bash {runsh}" if os.path.isfile(runsh) else f"python3 {script}"
    bn = os.path.basename(script)
    if os.environ.get("TMUX"):
        os.system(f'tmux set-option mouse on')
        os.system(f'tmux split-window -h -l 20 "{launcher} compact"')
        print(f"  宠物已停靠在右侧窗格！")
        print(f"  {DIM}鼠标点击宠物窗格即可互动 | 关闭: python3 {bn} undock{RST}")
    else:
        os.system(f'tmux new-session -d -s buddy')
        os.system(f'tmux set-option -t buddy mouse on')
        os.system(f'tmux split-window -h -t buddy -l 20 '
                  f'"{launcher} compact; tmux kill-session -t buddy"')
        os.system(f'tmux select-pane -t buddy:0.0')
        os.system(f'tmux send-keys -t buddy:0.0 '
                  f'"echo \\"  宠物在右边！鼠标点击宠物窗格即可互动\\"" Enter')
        os.system(f'tmux send-keys -t buddy:0.0 '
                  f'"echo \\"  关闭宠物: python3 {bn} undock\\"" Enter')
        os.system(f'tmux attach -t buddy')


def undock_companion():
    import shutil, subprocess
    if not shutil.which("tmux"):
        return
    if os.environ.get("TMUX"):
        result = subprocess.run(
            ["tmux", "list-panes", "-F", "#{pane_id} #{pane_current_command}"],
            capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            parts = line.split(None, 1)
            if len(parts) == 2 and "python" in parts[1].lower():
                os.system(f"tmux send-keys -t {parts[0]} C-c")
        print(f"  已向宠物窗格发送退出指令")
    else:
        result = subprocess.run(
            ["tmux", "has-session", "-t", "buddy"],
            capture_output=True)
        if result.returncode == 0:
            os.system("tmux kill-session -t buddy")
            print(f"  已关闭后台宠物 session")
        else:
            print(f"  没有找到运行中的宠物")
