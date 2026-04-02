#!/usr/bin/env python3
"""Buddy Pet — 终端电子宠物 (移植自 Claude Code)"""

import os, sys
# 自动加载 vendor/ 目录中的依赖（内网部署用）
# 如果系统已安装 llama_cpp（例如 GPU 版），优先用系统的
# 否则检查 vendor 的 cpython .so 是否匹配当前 Python 版本
_vendor = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
_need_vendor = True
try:
    import llama_cpp as _test_llm
    _need_vendor = False  # 系统已安装，不用 vendor
    del _test_llm
except ImportError:
    pass
if _need_vendor and os.path.isdir(_vendor) and _vendor not in sys.path:
    _pytag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    _use_vendor = True
    for _root, _dirs, _files in os.walk(_vendor):
        for _f in _files:
            if ".cpython-" in _f and _f.endswith(".so"):
                _use_vendor = _pytag in _f
                break
        if not _use_vendor:
            break
    if _use_vendor:
        sys.path.insert(0, _vendor)

import argparse
import time
import uuid

from buddypet.constants import BOLD, DIM, RST, SPECIES_ZH
from buddypet.prng import roll_companion
from buddypet.config import load_config, save_config, dock_companion, undock_companion
from buddypet.terminal import (
    render_card, interactive_loop, hatch_animation, idle_animation,
    pet_once, show_gallery, show_odds, search_legendary,
)
from buddypet.chat import chat_mode


def main():
    p = argparse.ArgumentParser(
        description="Buddy Pet — 终端电子宠物 (移植自 Claude Code)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  buddy.py hatch                  首次孵化你的伙伴
  buddy.py hatch --id <user_id>   用指定 ID 孵化
  buddy.py show                   查看伙伴卡片
  buddy.py pet                    摸摸 (原版 /buddy pet)
  buddy.py chat                   和宠物聊天
  buddy.py dock                   tmux 分屏常驻
  buddy.py undock                 关闭常驻宠物
  buddy.py live                   全屏互动 (摸/喂/聊/戳)
  buddy.py idle                   纯观赏动画
  buddy.py gallery                全物种图鉴
  buddy.py odds                   稀有度概率表
  buddy.py roll <seed>            试抽
  buddy.py search                 搜索 Legendary
  buddy.py reset                  重置
""")
    sub = p.add_subparsers(dest="cmd")

    h = sub.add_parser("hatch", help="孵化你的专属伙伴")
    h.add_argument("--id", help="指定 userId")
    h.add_argument("--name", help="起名字")

    sub.add_parser("show",    help="查看伙伴卡片")
    sub.add_parser("pet",     help="摸摸 (原版 /buddy pet)")
    sub.add_parser("chat",    help="和宠物聊天")
    sub.add_parser("live",    help="全屏互动模式")
    sub.add_parser("dock",    help="tmux 分屏常驻")
    sub.add_parser("undock",  help="关闭常驻宠物")
    sub.add_parser("compact", help=argparse.SUPPRESS)
    sub.add_parser("idle",    help="纯观赏动画")
    sub.add_parser("gallery", help="全物种图鉴")
    sub.add_parser("odds",    help="稀有度概率表")

    r = sub.add_parser("roll", help="试抽")
    r.add_argument("seed", help="种子字符串")

    s = sub.add_parser("search", help="搜索 Legendary")
    s.add_argument("-n", type=int, default=10)

    sub.add_parser("reset",   help="重置伙伴")
    rn = sub.add_parser("rename", help="改名")
    rn.add_argument("name")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        return

    cfg = load_config()

    def need_companion():
        if not cfg.get("companion"):
            print(f"\n  还没有伙伴！用 'hatch' 孵化。\n")
            return None, None
        co = roll_companion(cfg["user_id"])
        nm = cfg["companion"].get("name", "???")
        return co, nm

    if args.cmd == "hatch":
        if cfg.get("companion"):
            print(f"\n  你已经有伙伴了！用 'show' 查看，'reset' 重新来。\n")
            print(render_card(roll_companion(cfg["user_id"]), cfg["companion"].get("name")))
            return
        uid = args.id or str(uuid.uuid4())
        co = roll_companion(uid)
        nm = args.name
        if not nm:
            dflt = f"小{SPECIES_ZH[co['species']]}"
            try: nm = input(f"  给你的{SPECIES_ZH[co['species']]}起名字 [{dflt}]: ").strip()
            except (EOFError, KeyboardInterrupt): nm = ""
            if not nm: nm = dflt
        cfg["user_id"] = uid
        cfg["companion"] = {"name": nm, "hatched_at": int(time.time())}
        save_config(cfg)
        hatch_animation(co, nm)

    elif args.cmd == "show":
        co, nm = need_companion()
        if not co: return
        print(); print(render_card(co, nm))
        ht = cfg["companion"].get("hatched_at", 0)
        if ht: print(f"  {DIM}相伴 {(int(time.time()) - ht) // 86400} 天{RST}")
        print()

    elif args.cmd == "pet":
        co, nm = need_companion()
        if not co: return
        pet_once(co, nm)

    elif args.cmd == "chat":
        co, nm = need_companion()
        if not co: return
        chat_mode(co, nm)

    elif args.cmd == "live":
        co, nm = need_companion()
        if not co: return
        interactive_loop(co, nm, compact_mode=False)

    elif args.cmd == "dock":
        dock_companion()

    elif args.cmd == "undock":
        undock_companion()

    elif args.cmd == "compact":
        co, nm = need_companion()
        if not co: return
        interactive_loop(co, nm, compact_mode=True)

    elif args.cmd == "idle":
        co, nm = need_companion()
        if not co: return
        idle_animation(co, nm)

    elif args.cmd == "gallery": show_gallery()
    elif args.cmd == "odds":    show_odds()

    elif args.cmd == "roll":
        print(); print(render_card(roll_companion(args.seed), f"[{args.seed}]")); print()

    elif args.cmd == "search":  search_legendary(args.n)

    elif args.cmd == "reset":
        if cfg.get("companion"):
            nm = cfg["companion"].get("name", "???")
            try: ok = input(f"  确定放走 {nm}？(y/N): ").strip().lower()
            except: ok = ""
            if ok == "y":
                del cfg["companion"]
                cfg.pop("user_id", None)
                save_config(cfg)
                print(f"  {nm} 走了... 👋")
            else: print("  取消。")
        else: print("  没有伙伴。")

    elif args.cmd == "rename":
        co, nm = need_companion()
        if not co: return
        cfg["companion"]["name"] = args.name
        save_config(cfg)
        print(f"  {nm} → {args.name}")


if __name__ == "__main__":
    main()
