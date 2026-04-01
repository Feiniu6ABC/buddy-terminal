# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Buddy Pet 是一个终端电子宠物系统。`buddy.py` + `buddypet/` 包是 Python 移植版，原版是 Claude Code 内部的 companion 系统（TypeScript/React/Ink），原版源码在 `buddy/` 目录下供参考。

## Running

```bash
python3 buddy.py <command>
```

Key commands: `hatch`, `show`, `pet`, `chat`, `live`, `dock`/`undock`, `idle`, `gallery`, `odds`, `roll <seed>`, `search`, `reset`, `rename <name>`.

No build step, no tests, no linting. stdlib only，零外部依赖。`buddy/` 下的 TS 文件仅作参考（依赖 Claude Code 的 React/Ink 框架）。

## Package Structure

```
buddy.py                  — CLI 入口 (argparse + 命令分发，~140行)
buddypet/
  __init__.py             — 包标记
  constants.py            — 所有数据常量: 稀有度、物种、外观、ANSI 颜色、动画参数
  prng.py                 — 确定性生成: mulberry32 PRNG, FNV-1a hash, roll_companion()
  sprites.py              — ASCII 精灵帧数据 (BODIES/HAT_LINES) + render_sprite/render_face
  terminal.py             — 终端工具 (dw/write_lines) + 卡片渲染 + 所有动画/交互模式 + 图鉴
  config.py               — JSON 配置持久化 (~/.buddy-pet.json) + tmux dock/undock
  chat.py                 — 离线对话引擎 (关键词匹配 + 模板回复)
buddy/                    — 原版 TS/React 源码 (参考用)
```

## Dependency Graph (无循环)

```
constants.py  ←── prng.py
     ↑               ↑
     │               │
sprites.py    ←── terminal.py  ←── chat.py
     ↑               ↑                ↑
     │               │                │
     └── config.py   └──── buddy.py ──┘
```

## Generation Flow (两版一致)

`userId + SALT` → FNV-1a hash → mulberry32 seed → 依次 roll: rarity → species → eye → hat → shiny → stats。相同 userId 永远产出相同 companion。SALT = `"friend-2026-401"`。

## Key Design Decisions

- 渲染用 cursor-home + line-clear (`\033[H` + `\033[K\r\n`)，`\r\n` 而非 `\n` 以兼容 raw 模式
- Linux/macOS only（`tty.setraw` + `termios` 做 raw input）
- dock 模式通过 tmux 实现，启用 `mouse on` 以兼容 VSCode 终端（VSCode 拦截 Ctrl+b）
- 对话引擎纯离线关键词匹配，无需联网

## Original (TS) vs Python Port 主要差异

| 方面 | 原版 (TS) | Python 版 |
|------|-----------|----------|
| 精灵帧 | 5行含帽子槽，智能跳过空行 | 4行 + hat insert |
| hat 渲染 | 仅 line 0 为空时替换 | 无条件 prepend |
| 渲染 | React/Ink 组件树 | 裸 ANSI 转义 |
| 窄屏阈值 | < 100 列 | < 16 列 |
| mood 系统 | 无 | Python 版自创 |
| 对话 | 无 | chat.py 关键词引擎 |
