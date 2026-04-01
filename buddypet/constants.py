"""常量定义 — 稀有度、物种、外观、动画参数、ANSI 颜色、基础工具"""

import os
import re
import unicodedata

# ─── 配置路径 ─────────────────────────────────────────

SALT = "friend-2026-401"
CONFIG_PATH = os.path.expanduser("~/.buddy-pet.json")

# ─── 稀有度 ──────────────────────────────────────────

RARITIES = ["common", "uncommon", "rare", "epic", "legendary"]
RARITY_WEIGHTS = {"common": 60, "uncommon": 25, "rare": 10, "epic": 4, "legendary": 1}
RARITY_STARS = {
    "common": "★", "uncommon": "★★", "rare": "★★★",
    "epic": "★★★★", "legendary": "★★★★★",
}
RARITY_COLORS = {
    "common": "\033[37m", "uncommon": "\033[32m", "rare": "\033[36m",
    "epic": "\033[35m", "legendary": "\033[33m",
}
RARITY_FLOOR = {"common": 5, "uncommon": 15, "rare": 25, "epic": 35, "legendary": 50}

# ─── 物种 / 外观 ─────────────────────────────────────

SPECIES = [
    "duck", "goose", "blob", "cat", "dragon", "octopus", "owl", "penguin",
    "turtle", "snail", "ghost", "axolotl", "capybara", "cactus", "robot",
    "rabbit", "mushroom", "chonk",
]
SPECIES_ZH = {
    "duck": "鸭子", "goose": "鹅", "blob": "果冻", "cat": "猫",
    "dragon": "龙", "octopus": "章鱼", "owl": "猫头鹰", "penguin": "企鹅",
    "turtle": "乌龟", "snail": "蜗牛", "ghost": "幽灵", "axolotl": "六角恐龙",
    "capybara": "水豚", "cactus": "仙人掌", "robot": "机器人", "rabbit": "兔子",
    "mushroom": "蘑菇", "chonk": "胖猫",
}
EYES = ["·", "✦", "×", "◉", "@", "°"]
HATS = ["none", "crown", "tophat", "propeller", "halo", "wizard", "beanie", "tinyduck"]
HATS_ZH = {
    "none": "无", "crown": "皇冠", "tophat": "礼帽", "propeller": "螺旋桨",
    "halo": "光环", "wizard": "巫师帽", "beanie": "毛线帽", "tinyduck": "头顶小鸭",
}
STAT_NAMES = ["DEBUGGING", "PATIENCE", "CHAOS", "WISDOM", "SNARK"]

# ─── ANSI 颜色 ──────────────────────────────────────

RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
SHINY = "\033[93;1m"

# ─── 动画参数 ───────────────────────────────────────

TICK_MS = 500
BUBBLE_SHOW = 20
FADE_WINDOW = 6
PET_BURST = 5
IDLE_SEQ = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0]

H = "♥"
PET_HEARTS = [
    f"   {H}    {H}   ", f"  {H}  {H}   {H}  ",
    f" {H}   {H}  {H}   ", f"{H}  {H}      {H} ", "·    ·   ·  ",
]

IDLE_BUBBLES = ["...", "zzZ", "~♪", ". . .", "*yawn*", "♪♫♪", "..zzz", "✧", "^^", "*stretch*"]
REACTION = {
    "pet":  ["purrrr~", "!!!", "♥♥♥", "(ᵔᴥᵔ)", "hehe~", "more!", "*happy*", "uwu", "nyaa~"],
    "feed": ["om nom nom", "*munch*", "yummy!", "♪~", "thanks!", "more pls?", "*chomp*"],
    "talk": ["hmm?", "tell me more!", "interesting...", "oh!", "really?", "*listens*", "wow!"],
    "poke": ["hey!", "!!?", "stop that!", "ow!", "*wobble*", "(>_<)", "rude!"],
}

# ─── 基础工具 ───────────────────────────────────────


def dw(s):
    """显示宽度 (CJK=2, ANSI转义码=0)"""
    clean = re.sub(r'\033\[[0-9;]*m', '', s)
    return sum(2 if unicodedata.east_asian_width(c) in ('F', 'W') else 1 for c in clean)
