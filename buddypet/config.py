"""配置持久化 + tmux dock/undock"""

import json
import os

from .constants import CONFIG_PATH, DIM, RST


def _find_tmux():
    """查找 tmux: 优先用自带的 bin/tmux，再找系统的"""
    import shutil
    bundled = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "tmux")
    if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
        # 设置库搜索路径
        lib_dir = os.path.join(os.path.dirname(bundled), "lib")
        if os.path.isdir(lib_dir):
            ld = os.environ.get("LD_LIBRARY_PATH", "")
            if lib_dir not in ld:
                os.environ["LD_LIBRARY_PATH"] = f"{lib_dir}:{ld}" if ld else lib_dir
        return bundled
    return shutil.which("tmux")


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
    import subprocess
    config = load_config()
    if not config.get("companion"):
        print("\n  No companion yet! Use 'hatch' first.\n")
        return

    tmux = _find_tmux()
    script = _entry_script()
    runsh = os.path.join(os.path.dirname(script), "run.sh")
    launcher = f"bash {runsh}" if os.path.isfile(runsh) else f"python3 {script}"
    bn = os.path.basename(script)

    if not tmux:
        # 无 tmux: 直接在当前终端运行 compact 模式
        print(f"  tmux not found, running in current terminal.")
        print(f"  {DIM}Tip: open another terminal for your work{RST}")
        print()
        os.execvp("bash", ["bash", "-c", f"{launcher} compact"]) if os.path.isfile(runsh) else \
            os.execvp("python3", ["python3", script, "compact"])
        return

    if os.environ.get("TMUX"):
        os.system(f'{tmux} set-option mouse on')
        os.system(f'{tmux} split-window -h -l 20 "{launcher} compact"')
        print(f"  宠物已停靠在右侧窗格！")
        print(f"  {DIM}鼠标点击宠物窗格即可互动 | 关闭: python3 {bn} undock{RST}")
    else:
        os.system(f'{tmux} new-session -d -s buddy')
        os.system(f'{tmux} set-option -t buddy mouse on')
        os.system(f'{tmux} split-window -h -t buddy -l 20 '
                  f'"{launcher} compact; {tmux} kill-session -t buddy"')
        os.system(f'{tmux} select-pane -t buddy:0.0')
        os.system(f'{tmux} send-keys -t buddy:0.0 '
                  f'"echo \\"  Pet is on the right! Click to interact\\"" Enter')
        os.system(f'{tmux} send-keys -t buddy:0.0 '
                  f'"echo \\"  Close: {bn} undock\\"" Enter')
        os.system(f'{tmux} attach -t buddy')


def undock_companion():
    import subprocess
    tmux = _find_tmux()
    if not tmux:
        return
    if os.environ.get("TMUX"):
        result = subprocess.run(
            [tmux, "list-panes", "-F", "#{pane_id} #{pane_current_command}"],
            capture_output=True, text=True)
        for line in result.stdout.strip().split("\n"):
            parts = line.split(None, 1)
            if len(parts) == 2 and "python" in parts[1].lower():
                os.system(f"{tmux} send-keys -t {parts[0]} C-c")
        print(f"  Sent exit signal to pet pane")
    else:
        result = subprocess.run(
            [tmux, "has-session", "-t", "buddy"],
            capture_output=True)
        if result.returncode == 0:
            os.system(f"{tmux} kill-session -t buddy")
            print(f"  Closed background pet session")
        else:
            print(f"  No running pet found")
