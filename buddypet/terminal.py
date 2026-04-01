"""终端工具、卡片渲染、动画、图鉴"""

import os
import sys
import time
import random
import select

from .constants import (
    BOLD, BUBBLE_SHOW, DIM, FADE_WINDOW, HATS_ZH, IDLE_BUBBLES, IDLE_SEQ,
    PET_BURST, PET_HEARTS, RARITIES, RARITY_COLORS, RARITY_STARS,
    RARITY_WEIGHTS, REACTION, RST, SHINY, SPECIES, SPECIES_ZH, TICK_MS,
    dw, wrap_text,
)
from .sprites import render_face, render_sprite
from .prng import mulberry32, roll_companion


def term_size():
    try:
        c, r = os.get_terminal_size()
        return c, r
    except OSError:
        return 80, 24


def write_lines(lines):
    """逐行原地刷新 — 光标归位 + 行尾清除，不闪烁"""
    _, rows = term_size()
    buf = "\033[H"
    n = min(len(lines), rows - 1)
    for i in range(n):
        buf += lines[i] + "\033[K\r\n"
    for _ in range(rows - 1 - n):
        buf += "\033[K\r\n"
    sys.stdout.write(buf)
    sys.stdout.flush()


# ─── 渲染卡片 ──────────────────────────────────────────


def render_card(comp, name=None):
    r = comp["rarity"]
    sp = comp["species"]
    c = SHINY if comp["shiny"] else RARITY_COLORS[r]
    lines = []
    lines.append(f"{c}{BOLD}{'═' * 44}{RST}")
    t = f"  {RARITY_STARS[r]} {r.upper()}"
    if comp["shiny"]: t += " ✨ SHINY"
    lines.append(f"{c}{BOLD}{t}{RST}")
    if name:
        lines.append(f"  {BOLD}{name}{RST} the {SPECIES_ZH[sp]} ({sp})")
    else:
        lines.append(f"  {SPECIES_ZH[sp]} ({sp})")
    lines.append(f"  眼睛: {comp['eye']}  帽子: {HATS_ZH[comp['hat']]}")
    lines.append(f"{c}{'─' * 44}{RST}")
    for sl in render_sprite(comp, 0):
        lines.append(f"{c}      {sl}{RST}")
    lines.append(f"{c}{'─' * 44}{RST}")
    lines.append(f"  {BOLD}属性{RST}")
    mx, mn = max(comp["stats"].values()), min(comp["stats"].values())
    for sn, v in comp["stats"].items():
        bar = "█" * (v // 5) + "░" * (20 - v // 5)
        m = f" {c}▲{RST}" if v == mx else (f" {DIM}▼{RST}" if v == mn else "")
        lines.append(f"    {sn:10s} {c}{bar}{RST} {v:3d}{m}")
    lines.append(f"{c}{BOLD}{'═' * 44}{RST}")
    return "\n".join(lines)


# ─── 交互引擎 ──────────────────────────────────────────


def interactive_loop(comp, name, compact_mode=False):
    """统一的交互循环 — 支持全屏和紧凑模式"""
    import tty, termios

    c = SHINY if comp["shiny"] else RARITY_COLORS[comp["rarity"]]
    stars = RARITY_STARS[comp["rarity"]]
    sp_zh = SPECIES_ZH[comp["species"]]

    tick = 0
    bubble = ""
    bubble_t = 0
    pet_t = -999
    mood = 100.0
    last_act = time.time()
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    bubble_dur = BUBBLE_SHOW  # 当前气泡显示时长 (ticks)
    _thinking = False         # LLM 正在生成中，阻塞输入

    def sbub(txt):
        nonlocal bubble, bubble_t, bubble_dur
        bubble, bubble_t = txt, tick
        # 根据文字长度动态调整显示时长: 基础10秒 + 每20字符多3秒
        length = dw(txt) if txt else 0
        bubble_dur = max(BUBBLE_SHOW, BUBBLE_SHOW + (length // 20) * 6)

    def build():
        cols, rows = term_size()
        lines = []

        petting = (tick - pet_t) < PET_BURST
        active_bub = bubble and (tick - bubble_t) < bubble_dur
        if petting or active_bub:
            sf = tick % 3; blink = False
        else:
            step = IDLE_SEQ[tick % len(IDLE_SEQ)]
            if step == -1: sf, blink = 0, True
            else: sf, blink = step % 3, False

        sprites = render_sprite(comp, sf)
        if blink:
            sprites = [l.replace(comp["eye"], "-") for l in sprites]

        if cols < 16:
            face = render_face(comp)
            hp = "\033[31m♥\033[0m " if petting else ""
            q = ""
            if active_bub:
                maxq = cols - dw(face) - 5
                q = f' "{bubble[:max(1,maxq)]}"'
            lines.append(f"{hp}{c}{BOLD}{face}{RST}{q}")
            lines.append(f"{DIM}{name}{RST}")
            lines.append(f"{DIM}p/f/t/k/q{RST}")
            return lines

        if compact_mode:
            mi = "\033[32m♥\033[0m" if mood > 70 else ("\033[33m~\033[0m" if mood > 40 else "\033[31m.\033[0m")
            lines.append(f" {c}{BOLD}{name}{RST} {mi}")
            lines.append(f" {c}{stars}{RST}")
        else:
            lines.append(f" {c}{BOLD}{stars} {name}{RST} ({sp_zh})")
            bl = min(20, cols // 3)
            fl = int(mood / (100 / bl))
            mc = "\033[32m" if mood > 70 else ("\033[33m" if mood > 40 else "\033[31m")
            lines.append(f" {mc}{'♥' * fl}{'·' * (bl - fl)}{RST} {int(mood)}")

        lines.append("")

        if petting and (tick - pet_t) < len(PET_HEARTS):
            lines.append(f" \033[31m{PET_HEARTS[tick - pet_t]}\033[0m")
        else:
            lines.append("")

        for sl in sprites:
            if compact_mode:
                pad = max(0, (cols - dw(sl.rstrip())) // 2)
                lines.append(f"{c}{' ' * pad}{sl.rstrip()}{RST}")
            else:
                lines.append(f"{c}  {sl}{RST}")

        lines.append("")

        if active_bub:
            age = tick - bubble_t
            fading = age >= bubble_dur - FADE_WINDOW
            bc = DIM if fading else ""
            inner_w = max(cols - 8, 10)
            wrapped = wrap_text(bubble, inner_w)
            if len(wrapped) > 3:
                wrapped = wrapped[:3]
                wrapped[-1] = wrapped[-1].rstrip() + "..."
            bw = max(dw(l) for l in wrapped) + 2
            lines.append(f" {bc}╭{'─' * bw}╮{RST}")
            for wl in wrapped:
                pad = bw - 2 - dw(wl)
                lines.append(f" {bc}│ {wl}{' ' * pad} │{RST}")
            lines.append(f" {bc}╰{'─' * bw}╯{RST}")
        else:
            lines += ["", "", ""]

        lines.append(f" {DIM}{'─' * (cols - 2)}{RST}")

        # 输入行 / 快捷键提示
        if input_buf is not None:
            lines.append(f" {BOLD}>{RST} {input_buf}\033[K")
        elif compact_mode:
            lines.append(f" {DIM}Type to chat | /p /f /k /q{RST}")
        else:
            lines.append(f" {DIM}Type to chat{RST} | {BOLD}/p{RST}et {BOLD}/f{RST}eed {BOLD}/k{RST}ick {BOLD}/q{RST}uit")

        return lines

    input_buf = None  # None=普通模式, str=正在输入
    next_idle_tick = random.randint(40, 80)  # 首次 idle: 20-40s 后
    start_time = time.time()
    next_reminder = 3600 + random.randint(-300, 300)  # ~55-65 min

    # 启动 idle 自言自语后台生成
    from .chat import start_idle_gen, stop_idle_gen
    start_idle_gen(name, comp)

    sys.stdout.write("\033[?25l\033[2J")
    sys.stdout.flush()

    try:
        tty.setraw(fd)
        while True:
            if select.select([sys.stdin], [], [], TICK_MS / 1000)[0]:
                ch = sys.stdin.read(1)
                if _thinking:
                    continue  # LLM 生成中，忽略所有按键
                if ch == '\x03':  # Ctrl+C 随时退出
                    if input_buf is not None:
                        input_buf = None
                        sys.stdout.write("\033[?25l")
                        sys.stdout.flush()
                    else:
                        break
                elif input_buf is not None:
                    # ── 聊天输入模式 ──
                    if ch in ('\r', '\n'):
                        msg = input_buf.strip()
                        input_buf = None
                        sys.stdout.write("\033[?25l")
                        sys.stdout.flush()
                        cmd = msg.lower()
                        if cmd in ('/q', '/quit', '/exit'):
                            break
                        elif cmd in ('/p', '/pet'):
                            pet_t = tick; mood = min(100, mood + 10); last_act = time.time()
                            sbub(random.choice(REACTION["pet"]))
                        elif cmd in ('/f', '/feed'):
                            mood = min(100, mood + 15); last_act = time.time()
                            sbub(random.choice(REACTION["feed"]))
                        elif cmd in ('/k', '/kick', '/poke'):
                            mood = max(0, mood - 5); last_act = time.time()
                            sbub(random.choice(REACTION["poke"]))
                        elif msg:
                            last_act = time.time()
                            _thinking = True
                            sbub("thinking...")
                            import threading as _th
                            from .chat import stop_idle_gen, start_idle_gen
                            stop_idle_gen()
                            def _bg_reply(m=msg):
                                nonlocal _thinking
                                try:
                                    from .chat import chat_reply, _load_history, _chat_history
                                    if not _chat_history:
                                        _load_history()
                                    r = chat_reply(m, name, comp)
                                    sbub(r if r else "(no response)")
                                except Exception as e:
                                    sbub(f"(error: {e})")
                                finally:
                                    _thinking = False
                                    start_idle_gen(name, comp)
                            _th.Thread(target=_bg_reply, daemon=True).start()
                    elif ch in ('\x7f', '\x08'):  # backspace
                        input_buf = input_buf[:-1]
                    elif ch == '\x1b':  # Esc 取消输入
                        input_buf = None
                        sys.stdout.write("\033[?25l")
                        sys.stdout.flush()
                    elif ch.isprintable():
                        input_buf += ch
                else:
                    # ── 任意键进入输入模式 ──
                    if ch.isprintable() and ch not in ('\r', '\n'):
                        input_buf = ch
                        sys.stdout.write("\033[?25h")
                        sys.stdout.flush()

            if time.time() - last_act > 120:
                mood = max(30, mood - 0.2)

            # 保持 "thinking..." 气泡不消失
            if _thinking and bubble == "thinking..." and (tick - bubble_t) >= bubble_dur - 2:
                bubble_t = tick

            if (not bubble or (tick - bubble_t) >= bubble_dur) and tick == next_idle_tick:
                from .chat import get_idle_bubble
                idle = get_idle_bubble()
                if idle:
                    sbub(idle)
                elif random.random() < 0.3:  # 30% chance for static fallback
                    sbub(random.choice(IDLE_BUBBLES))
                # next idle: 40-80 seconds (80-160 ticks)
                next_idle_tick = tick + random.randint(80, 160)

            # 定时关怀提醒 (~1hr)
            elapsed = time.time() - start_time
            if elapsed >= next_reminder:
                from .chat import get_care_reminder
                reminder = get_care_reminder(name, comp)
                if reminder:
                    sbub(reminder)
                next_reminder = elapsed + 3600 + random.randint(-300, 300)

            write_lines(build())
            tick += 1
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop_idle_gen()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()
        print(f"  {name}: bye~ 👋\n")


# ─── 孵化动画 ──────────────────────────────────────────

EGG = [
    ["    .--.    ", "   /    \\   ", "  |      |  ", "   \\    /   ", "    `--´    "],
    ["    .--.    ", "   / .  \\   ", "  |  .   |  ", "   \\    /   ", "    `--´    "],
    ["    .--.    ", "   / . .\\   ", "  |  \\ / |  ", "   \\  . /   ", "    `--´    "],
    ["    .--. *  ", "  ./ . .\\   ", "  | \\/\\/ |  ", "   \\ .. / * ", "    `--´    "],
    [" *  .--. *  ", "  / .||. \\  ", "  |/ .. \\|  ", "   \\|..|/ * ", "    `--´    "],
    ["  *  **  *  ", "    *  *    ", "  *  **  *  ", "    *  *    ", "  *  **  *  "],
]


def hatch_animation(comp, name):
    c = SHINY if comp["shiny"] else RARITY_COLORS[comp["rarity"]]
    hide, show = "\033[?25l", "\033[?25h"
    sys.stdout.write(hide)
    sys.stdout.flush()
    try:
        for i, egg in enumerate(EGG):
            lines = ["", f"  {DIM}正在孵化...{RST}", ""]
            for el in egg:
                lines.append(f"      {el}")
            lines.append("")
            lines.append(f"      {DIM}{'.' * (i + 1)}{RST}")
            write_lines(lines)
            time.sleep(0.5)

        write_lines(["", f"  {c}{BOLD}✨ 孵化成功！✨{RST}"])
        time.sleep(0.8)

        card = render_card(comp, name).split("\n")
        write_lines([""] + card)
    finally:
        sys.stdout.write(show)
        sys.stdout.flush()


# ─── Idle 纯动画 ────────────────────────────────────────


def idle_animation(comp, name):
    c = SHINY if comp["shiny"] else RARITY_COLORS[comp["rarity"]]
    stars = RARITY_STARS[comp["rarity"]]
    sp_zh = SPECIES_ZH[comp["species"]]
    quotes = IDLE_BUBBLES[:]
    frame = 0
    rng = mulberry32(int(time.time()) & 0xFFFFFFFF)

    sys.stdout.write("\033[?25l\033[2J")
    sys.stdout.flush()
    try:
        while True:
            lines = []
            lines.append(f"  {c}{BOLD}{stars} {name} the {sp_zh}{RST}")
            lines.append(f"  {DIM}Ctrl+C 退出{RST}")
            lines.append("")
            for sl in render_sprite(comp, frame):
                lines.append(f"{c}      {sl}{RST}")
            if frame % 3 == 0:
                q = quotes[int(rng() * len(quotes)) % len(quotes)]
                bw = dw(q) + 2
                lines.append(f"        ╭{'─' * bw}╮")
                lines.append(f"        │ {q} │")
                lines.append(f"        ╰{'─' * bw}╯")
            else:
                lines += ["", "", ""]
            write_lines(lines)
            frame += 1
            time.sleep(0.8)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()


# ─── Pet 快速摸一下 ──────────────────────────────────────


def pet_once(comp, name):
    c = SHINY if comp["shiny"] else RARITY_COLORS[comp["rarity"]]
    react = random.choice(REACTION["pet"])
    sys.stdout.write("\033[?25l\033[2J")
    sys.stdout.flush()
    try:
        for t in range(PET_BURST + 2):
            lines = [""]
            if t < len(PET_HEARTS):
                lines.append(f"    \033[31m{PET_HEARTS[t]}\033[0m")
            else:
                lines.append("")
            for sl in render_sprite(comp, t % 3):
                lines.append(f"{c}    {sl}{RST}")
            bw = dw(react) + 2
            lines.append(f"      ╭{'─' * bw}╮")
            lines.append(f"      │ {react} │")
            lines.append(f"      ╰{'─' * bw}╯")
            lines.append("")
            lines.append(f"  {BOLD}{name}{RST}: {react}")
            write_lines(lines)
            time.sleep(0.4)
    finally:
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()
    print(f"  {name}: {react}\n")


# ─── 图鉴 / 概率 / 搜索 ────────────────────────────────


def show_gallery():
    print(f"\n  {BOLD}═══ 物种图鉴 ({len(SPECIES)} 种) ═══{RST}\n")
    for i in range(0, len(SPECIES), 3):
        batch = SPECIES[i:i+3]
        sprites = []
        for sp in batch:
            co = {"species": sp, "eye": "·", "hat": "none", "rarity": "common", "shiny": False}
            sprites.append(render_sprite(co, 0))
        mx = max(len(s) for s in sprites)
        for s in sprites:
            while len(s) < mx: s.insert(0, "            ")
        hdr = ""
        for sp in batch:
            hdr += f"  {SPECIES_ZH[sp] + '(' + sp + ')':^18s}"
        print(hdr)
        for row in range(mx):
            ln = ""
            for j in range(len(batch)):
                ln += f"  {sprites[j][row]:18s}"
            print(ln)
        print()
    print(f"  {DIM}帽子: 皇冠/礼帽/螺旋桨/光环/巫师帽/毛线帽/头顶小鸭 (common 无帽){RST}")
    print(f"  {DIM}眼睛: · ✦ × ◉ @ °{RST}\n")


def show_odds():
    print(f"\n  {BOLD}═══ 稀有度概率 ═══{RST}\n")
    for r in RARITIES:
        w = RARITY_WEIGHTS[r]
        print(f"  {RARITY_COLORS[r]}{RARITY_STARS[r]:5s} {r:10s} {'█' * w}{'░' * (60-w)} {w}%{RST}")
    print(f"\n  {DIM}闪光(Shiny): 1%  最稀有: Legendary+Shiny = 0.01%{RST}\n")


def search_legendary(n=10):
    print(f"\n  {BOLD}搜索 Legendary...{RST}")
    found = sh = 0
    for i in range(1000000):
        co = roll_companion(f"seed-{i:08d}")
        if co["rarity"] == "legendary":
            found += 1
            s = "✨SHINY" if co["shiny"] else ""
            cl = SHINY if co["shiny"] else RARITY_COLORS["legendary"]
            print(f"  {cl}★★★★★ {SPECIES_ZH[co['species']]}({co['species']}) 眼={co['eye']} 帽={HATS_ZH[co['hat']]} {s}{RST}  (seed-{i:08d})")
            if co["shiny"]: sh += 1
            if found >= n: break
    print(f"\n  {DIM}{i+1} 个种子中 {found} 个 Legendary ({sh} 个 Shiny){RST}\n")
