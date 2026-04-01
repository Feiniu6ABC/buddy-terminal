"""确定性生成 — PRNG、哈希、roll 函数"""

import math

from .constants import (
    EYES, HATS, RARITIES, RARITY_FLOOR, RARITY_WEIGHTS,
    SALT, SPECIES, STAT_NAMES,
)


def mulberry32(seed):
    a = seed & 0xFFFFFFFF
    def rng():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = (a ^ (a >> 15)) & 0xFFFFFFFF
        t = (t * ((1 | a) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t2 = (t ^ (t >> 7)) & 0xFFFFFFFF
        t = (t + (t2 * ((61 | t2) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return rng


def hash_string(s):
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def pick(rng, arr):
    return arr[int(math.floor(rng() * len(arr)))]


def roll_rarity(rng):
    total = sum(RARITY_WEIGHTS.values())
    roll = rng() * total
    for r in RARITIES:
        roll -= RARITY_WEIGHTS[r]
        if roll < 0: return r
    return "common"


def roll_stats(rng, rarity):
    floor = RARITY_FLOOR[rarity]
    peak = pick(rng, STAT_NAMES)
    dump = pick(rng, STAT_NAMES)
    while dump == peak: dump = pick(rng, STAT_NAMES)
    stats = {}
    for n in STAT_NAMES:
        if n == peak:   stats[n] = min(100, floor + 50 + int(rng() * 30))
        elif n == dump:  stats[n] = max(1, floor - 10 + int(rng() * 15))
        else:            stats[n] = floor + int(rng() * 40)
    return stats


def roll_companion(user_id):
    rng = mulberry32(hash_string(user_id + SALT))
    rarity = roll_rarity(rng)
    return {
        "rarity": rarity, "species": pick(rng, SPECIES),
        "eye": pick(rng, EYES),
        "hat": "none" if rarity == "common" else pick(rng, HATS),
        "shiny": rng() < 0.01, "stats": roll_stats(rng, rarity),
    }
