"""离线对话引擎 — LLM 优先，关键词 fallback"""

import os
import time
import random

from .constants import BOLD, DIM, RARITY_COLORS, RST, SHINY, SPECIES_ZH, dw, render_bubble
from .sprites import render_face

# ─── LLM 引擎 ────────────────────────────────────────

_llm = None
_llm_checked = False

# 模型搜索路径: 项目 models/ 目录，或环境变量指定
MODEL_SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"),
]
MODEL_GLOB = "*.gguf"


def _find_model():
    """搜索本地 GGUF 模型文件，返回路径或 None"""
    env_path = os.environ.get("BUDDY_MODEL")
    if env_path and os.path.isfile(env_path):
        return env_path
    import glob
    for d in MODEL_SEARCH_PATHS:
        files = sorted(glob.glob(os.path.join(d, MODEL_GLOB)), key=os.path.getsize, reverse=True)
        if files:
            return files[0]  # 优先用最大的模型
    return None


def _get_llm():
    """懒加载 LLM，加载失败返回 None"""
    global _llm, _llm_checked
    if _llm_checked:
        return _llm
    _llm_checked = True
    model_path = _find_model()
    if not model_path:
        return None
    try:
        from llama_cpp import Llama
        _llm = Llama(
            model_path=model_path,
            n_ctx=1024,
            n_threads=4,
            verbose=False,
        )
    except Exception:
        _llm = None
    return _llm


# 属性 → 性格描述 (5档: very low / low / mid / high / very high)
_STAT_PERSONALITY = {
    "DEBUGGING": [
        "You're clueless about tech, often giving wrong answers with full confidence",
        "You're fuzzy on technical details, often mixing up concepts but trying your best",
        "You understand basic tech questions, occasionally making small mistakes",
        "You're sharp and analytical, love digging into root causes methodically",
        "You're a tech genius, obsessed with analyzing everything, sometimes over-engineering",
    ],
    "PATIENCE": [
        "You're extremely impatient, want to answer in one word, often skip explanations",
        "You're hasty, give short direct answers, sometimes rush the user",
        "Your patience is average, willing to explain simple things but lazy on complex ones",
        "You're very patient, willing to explain step by step, never rushing",
        "You're patient to the point of being verbose, always over-explaining every detail",
    ],
    "CHAOS": [
        "You're extremely rigid and serious, never joke, everything by the book",
        "You're steady and reliable, speak in order, rarely loosen up",
        "You sometimes serious sometimes playful, depends on your mood",
        "You're wildly creative, often go off-topic or blurt out random ideas",
        "You're completely unpredictable, may say bizarre things at any moment",
    ],
    "WISDOM": [
        "You're naive and simple-minded, your understanding of the world is childlike",
        "You're more emotional than analytical, not great at deep thinking but rich in feelings",
        "You have basic common sense and opinions, not brilliant but not dumb",
        "You're knowledgeable, like to reference things, seem well-informed",
        "You're a little philosopher, always seeing things from a deeper angle",
    ],
    "SNARK": [
        "You're sickeningly sweet, all compliments and cuddles, never a harsh word",
        "You're gentle and caring, always soft-spoken, only occasionally tease",
        "You're neither sweet nor snarky, occasionally quip but nothing extreme",
        "You're snarky and love to roast, often use sarcasm to show you care",
        "You're savage to the bone, nearly every sentence has a sting, but deep down you care",
    ],
}

def _stat_tier(val):
    """属性值映射到5档: 0-20极低, 21-40低, 41-60中, 61-80高, 81-100极高"""
    if val <= 20: return 0
    if val <= 40: return 1
    if val <= 60: return 2
    if val <= 80: return 3
    return 4


def _build_system_prompt(name, comp):
    sp_zh = SPECIES_ZH.get(comp["species"], comp["species"])
    stats = comp["stats"]
    peak = max(stats, key=stats.get)
    dump = min(stats, key=stats.get)

    # 根据属性值生成性格描述 (5档)
    traits = []
    for stat, val in stats.items():
        if stat in _STAT_PERSONALITY:
            traits.append(_STAT_PERSONALITY[stat][_stat_tier(val)])
    personality = "; ".join(traits) + "."

    return (
        f"You are {name}, a {sp_zh} ({comp['species']}) living in your owner's terminal. "
        f"Your owner hatched you and you are deeply attached to them.\n"
        f"Your personality: {personality}\n"
        f"Rules:\n"
        f"- Always stay in character as a {sp_zh}, never say you are an AI or program\n"
        f"- Always reply in English\n"
        f"- For casual chat: be cute and brief, use kaomoji occasionally\n"
        f"- IMPORTANT: For technical questions, give the CORRECT answer first. "
        f"Never give wrong commands on purpose even if your personality is 'fuzzy'. "
        f"Personality only affects tone, NOT accuracy\n"
        f"- Keep replies under 3 sentences"
    )

# LLM 对话历史 — 持久化到文件
_chat_history = []       # 完整历史 (全部持久化到磁盘)
_chat_total = 0          # 总对话条数 (用于闪光成就)
_LLM_CONTEXT = 20        # 送入 LLM 的最近对话条数
_HISTORY_PATH = os.path.expanduser("~/.buddy-pet-history.json")


def _load_history():
    """从文件加载历史对话"""
    global _chat_history, _chat_total
    try:
        if os.path.exists(_HISTORY_PATH):
            import json
            with open(_HISTORY_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _chat_history = data.get("messages", [])
                _chat_total = data.get("total", len(_chat_history))
            else:
                # 兼容旧格式 (纯列表)
                _chat_history = data
                _chat_total = len(data)
    except Exception:
        _chat_history = []
        _chat_total = 0


def _save_history():
    """保存历史对话到文件"""
    try:
        import json
        with open(_HISTORY_PATH, "w") as f:
            json.dump({
                "messages": _chat_history,
                "total": _chat_total,
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_chat_total():
    """返回总对话条数"""
    return _chat_total


def _llm_reply(user_input, name, comp):
    """用本地 LLM 生成回复"""
    llm = _get_llm()
    if llm is None:
        return None
    system_prompt = _build_system_prompt(name, comp)
    global _chat_total
    _chat_history.append({"role": "user", "content": user_input})
    recent = _chat_history[-_LLM_CONTEXT:]
    messages = [{"role": "system", "content": system_prompt}] + recent
    try:
        with _llm_lock:
            result = llm.create_chat_completion(
                messages=messages,
                max_tokens=512,
                temperature=0.7,
            )
        reply = result["choices"][0]["message"]["content"].strip()
        # Qwen3 会输出 <think>...</think> 思考过程，只保留最终回复
        import re as _re
        reply = _re.sub(r'<think>[\s\S]*?</think>\s*', '', reply).strip()
        # 如果思考过程没闭合（被截断），丢弃整个 think 块
        if '<think>' in reply:
            reply = reply.split('</think>')[-1].strip() if '</think>' in reply else ""
        if not reply:
            _chat_history.pop()  # 回滚 user 消息
            return None
        _chat_history.append({"role": "assistant", "content": reply})
        _chat_total += 2  # user + assistant
        _save_history()
        return reply
    except Exception:
        _chat_history.pop()  # 回滚 user 消息
        return None


# ─── LLM 线程安全锁 ──────────────────────────────────
import threading, queue
_llm_lock = threading.Lock()

_idle_queue = queue.Queue(maxsize=5)
_idle_thread = None
_idle_stop = threading.Event()


# 物种特有的 idle 行为提示
_SPECIES_IDLE_HINTS = {
    "cat":      "You purr, nap, chase imaginary mice, stare at cursors, knead keyboards, groom yourself",
    "duck":     "You quack softly, waddle around, splash in puddles, preen your feathers, float serenely",
    "goose":    "You honk at things, stand guard aggressively, chase bugs, steal snacks, strut proudly",
    "blob":     "You wobble, ooze around, absorb things, jiggle contentedly, blob out in odd shapes",
    "dragon":   "You breathe tiny sparks, guard your treasure hoard, survey your domain, sharpen claws",
    "octopus":  "You wave your tentacles, change colors, squeeze into small spaces, ink when startled",
    "owl":      "You hoot softly, rotate your head, watch everything, ponder deeply, perch silently",
    "penguin":  "You waddle, slide on your belly, fish for data, huddle for warmth, flap your flippers",
    "turtle":   "You move slowly, retreat into your shell, bask in warmth, carry wisdom patiently",
    "snail":    "You slide slowly, leave a trail, hide in your shell, munch on leaves, enjoy the rain",
    "ghost":    "You float through walls, go invisible, say boo, haunt the terminal, flicker spookily",
    "axolotl":  "You smile permanently, wave your gills, swim lazily, regenerate, look adorable",
    "capybara": "You chill, sit in warm water, befriend everyone, munch grass, radiate calm energy",
    "cactus":   "You stand still, photosynthesize, grow tiny flowers, store water, poke passersby",
    "robot":    "You beep, run diagnostics, compute things, flash LEDs, recalibrate your sensors",
}


def _build_idle_prompt(name, comp):
    species = comp["species"]
    sp_zh = SPECIES_ZH.get(species, species)
    stats = comp["stats"]
    hints = _SPECIES_IDLE_HINTS.get(species, f"You act like a typical {species}")

    # 根据属性调整 idle 风格
    peak = max(stats, key=stats.get)
    style_hints = []
    if stats.get("CHAOS", 50) > 60:
        style_hints.append("your thoughts are random and unpredictable")
    if stats.get("WISDOM", 50) > 60:
        style_hints.append("you sometimes have deep or philosophical thoughts")
    if stats.get("SNARK", 50) > 60:
        style_hints.append("your mumbles can be sarcastic or grumpy")
    if stats.get("PATIENCE", 50) < 30:
        style_hints.append("you're restless and fidgety")
    style = "; ".join(style_hints) if style_hints else "you're calm and content"

    return (
        f"You are {name}, a {sp_zh} ({species}) living in a terminal. "
        f"{hints}. Also, {style}.\n"
        f"Generate a single short idle thought, action, or mumble (under 8 words). "
        f"Be creative and varied. No two thoughts should be the same. "
        f"English only. Output ONLY the thought, nothing else."
    )


def _idle_worker(name, comp):
    """Background thread: pre-generate idle thoughts into a queue."""
    llm = _get_llm()
    if llm is None:
        return
    prompt = _build_idle_prompt(name, comp)
    # 用不同的 "user" 消息来增加多样性
    prompts_pool = [
        "What are you thinking?", "What are you doing?",
        "Say something.", "What do you see?",
        "How do you feel?", "What's on your mind?",
    ]
    idx = 0
    while not _idle_stop.is_set():
        try:
            with _llm_lock:
                result = llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": prompts_pool[idx % len(prompts_pool)]},
                    ],
                    max_tokens=32,
                    temperature=1.0,
                )
            idx += 1
            text = result["choices"][0]["message"]["content"].strip()
            import re as _re
            text = _re.sub(r'<think>[\s\S]*?</think>\s*', '', text).strip()
            if '<think>' in text:
                text = ""
            text = text.strip('"\'')
            if text and len(text) < 60:
                _idle_queue.put(text, timeout=60)
        except Exception:
            pass
        # 队列不满就立刻生成下一条，满了才等
        if _idle_queue.full():
            _idle_stop.wait(30)
        else:
            _idle_stop.wait(2)


def start_idle_gen(name, comp):
    """启动 idle 生成后台线程"""
    global _idle_thread
    # 确保旧线程已停止
    if _idle_thread and _idle_thread.is_alive():
        _idle_stop.set()
        _idle_thread.join(timeout=3)
    _idle_stop.clear()
    _idle_thread = threading.Thread(target=_idle_worker, args=(name, comp), daemon=True)
    _idle_thread.start()


def stop_idle_gen():
    """停止 idle 生成"""
    _idle_stop.set()


def get_idle_bubble():
    """取一条预生成的 idle 自言自语，没有就返回 None"""
    try:
        return _idle_queue.get_nowait()
    except queue.Empty:
        return None


def get_care_reminder(name, comp):
    """生成关怀提醒（喝水、休息等），用 LLM 或 fallback"""
    llm = _get_llm()
    sp_zh = SPECIES_ZH.get(comp["species"], comp["species"])
    if llm:
        try:
            with _llm_lock:
                result = llm.create_chat_completion(
                    messages=[
                        {"role": "system", "content":
                            f"You are {name}, a {sp_zh} ({comp['species']}). "
                            f"Your owner has been working for over an hour. "
                            f"Remind them to take a break in your own style. "
                            f"Suggest ONE of: drink water, stretch, rest eyes, take a walk, grab a snack. "
                            f"Keep it under 10 words, cute and caring. English only."},
                        {"role": "user", "content": "Remind me."},
                    ],
                    max_tokens=32,
                    temperature=0.9,
                )
            text = result["choices"][0]["message"]["content"].strip()
            import re as _re
            text = _re.sub(r'<think>[\s\S]*?</think>\s*', '', text).strip()
            if '<think>' in text:
                text = ""
            text = text.strip('"\'')
            if text and len(text) < 60:
                return text
        except Exception:
            pass
    # fallback
    import random as _rand
    fallbacks = [
        f"Hey! {name} says drink some water!",
        f"*nudge* Take a break, stretch a bit!",
        f"Your eyes need rest! Look away for 20s~",
        f"*poke* Go grab a snack, you deserve it!",
        f"Stand up and stretch! {name} is watching~",
    ]
    return _rand.choice(fallbacks)


# ─── 关键词 fallback 引擎 ──────────────────────────────

CHAT_RULES = [
    (["hi", "hello", "hey", "yo", "sup"],
     ["{name} stretches: hey there~", "Yay! You're here! {name} is happy!",
      "{name} tilts head: heya~", "Hello! Let's have a great day!"]),
    (["good night", "gn", "sleep", "bedtime"],
     ["Night night~ {name} is sleepy too zzZ", "{name} yawns: good night...",
      "Sweet dreams! {name} will watch over you~"]),
    (["your name", "who are you", "what are you"],
     ["I'm {name}! A {species}!", "{name}! {name}! Remember it?",
      "I'm your buddy {name}~ a {species} ^^"]),
    (["how are you", "how do you feel", "you ok"],
     ["{name} bounces: super happy!", "I'm great with you around~",
      "My {peak} stat feels extra high today!", "{name} wags: doing great~"]),
    (["happy", "nice", "awesome", "great", "yay"],
     ["Your joy makes {name} happy too!", "(ᵔᴥᵔ) yay together!", "{name} bounces along~"]),
    (["sad", "tired", "stressed", "frustrated", "exhausted", "upset"],
     ["{name} nuzzles you: it'll be okay...", "*pat pat* {name} is here for you",
      "{name} sits quietly beside you", "Hang in there... take a break",
      "{name} offers you an imaginary snack"]),
    (["bug", "error", "crash", "broken", "fail"],
     ["{name} tilts head: is a bug tasty?", "Don't panic! {name}'s DEBUGGING is... decent",
      "Maybe take a break first?", "{name} stares at the screen: ...confused"]),
    (["code", "coding", "debug", "programming"],
     ["You got this! {name} cheers you on!", "{name} pretends to understand your code",
      "Don't forget to rest~", "{name} sits by the keyboard quietly"]),
    (["deploy", "release", "ship", "launch"],
     ["{name} covers eyes nervously: is it time?", "Good luck! {name} is praying!",
      "Ship it! (ᵔᴥᵔ)"]),
    (["hungry", "food", "lunch", "dinner", "snack", "eat"],
     ["{name}: I want food too!", "Did someone say snacks??",
      "{name}'s eyes light up: got treats?", "Go eat something, don't starve~"]),
    (["feed", "treat", "give you"],
     ["om nom nom~ yummy!", "{name} eats happily: thanks!", "*chomp chomp* more?"]),
    (["pet", "cute", "good boy", "good girl", "adorable"],
     ["purrrr~ ♥", "{name} closes eyes happily", "(ᵔᴥᵔ) hehe~", "More pets! More pets!"]),
    (["bored", "nothing to do"],
     ["{name} is bored too... wanna stare at nothing together?", "Then... pet me?",
      "{name} rolls over: let's just chill~"]),
    (["time", "what time", "clock"],
     ["It's {hour} o'clock~", "{name} checks the clock: {hour}:{minute}",
      "{timegreet}"]),
    (["thanks", "thank you", "thx"],
     ["No problem~ {name} is always here!", "Hehe, happy to help~",
      "Anytime! Just call {name}!"]),
    (["bye", "goodbye", "see you", "leaving", "gotta go"],
     ["{name} waves: bye~ come back soon!", "See ya! {name} will miss you~",
      "Bye! Don't forget about {name}!"]),
]

CHAT_FALLBACK = [
    "{name} tilts head: hmm...?", "Oh! ... {name} didn't quite get that",
    "{name} nods thoughtfully", "...{name}'s WISDOM isn't enough for this",
    "{name} blinks: say that again?", "Uh huh! ({name} is listening! probably)",
    "{name} pats you with a tiny paw: go on~", "*tilts head* ...?",
    "{name} doesn't understand but will always be here for you!",
]


def _chat_format(text, name, species, comp):
    peak = max(comp["stats"], key=comp["stats"].get)
    now = time.localtime()
    hour = now.tm_hour
    if hour < 6:     tg = "It's so late, go to sleep!"
    elif hour < 12:  tg = "Good morning~ let's have a great day!"
    elif hour < 14:  tg = "Lunchtime! Go eat something!"
    elif hour < 18:  tg = "Afternoon~ hang in there!"
    else:            tg = "Evening~ don't stay up too late!"
    return (text
            .replace("{name}", name)
            .replace("{species}", SPECIES_ZH.get(species, species))
            .replace("{peak}", peak)
            .replace("{hour}", str(hour))
            .replace("{minute}", f"{now.tm_min:02d}")
            .replace("{timegreet}", tg))


def _keyword_reply(user_input, name, comp):
    low = user_input.lower().strip()
    if not low:
        return random.choice(["...", "{name} waits quietly~"]).replace("{name}", name)
    for keywords, replies in CHAT_RULES:
        if any(kw in low for kw in keywords):
            return _chat_format(random.choice(replies), name, comp["species"], comp)
    return _chat_format(random.choice(CHAT_FALLBACK), name, comp["species"], comp)


# ─── 统一接口 ────────────────────────────────────────


def chat_reply(user_input, name, comp):
    """LLM 优先，失败则 fallback 到关键词"""
    if not user_input.strip():
        return _keyword_reply(user_input, name, comp)
    reply = _llm_reply(user_input, name, comp)
    if reply:
        return reply
    return _keyword_reply(user_input, name, comp)


def chat_mode(comp, name):
    """交互式对话模式"""
    c = SHINY if comp["shiny"] else RARITY_COLORS[comp["rarity"]]
    sp_zh = SPECIES_ZH[comp["species"]]
    face = render_face(comp)

    # 加载历史对话 & 检测引擎
    _load_history()
    has_llm = _find_model() is not None
    if has_llm:
        print(f"\n  {DIM}Loading model...{RST}", end="", flush=True)
        _get_llm()
        engine = "LLM" if _llm else "keyword"
        print(f"\r\033[K", end="")
    else:
        engine = "keyword"

    print(f"\n  {c}{BOLD}{face} {name}{RST} ({sp_zh})")
    print(f"  {DIM}Engine: {engine} | Type message + Enter, q to quit{RST}")
    print(f"  {DIM}{'─' * 40}{RST}")

    try:
        while True:
            try:
                msg = input(f"  {BOLD}You:{RST} ")
            except EOFError:
                break
            if msg.strip().lower() in ('q', 'quit', 'exit', ':q'):
                break
            reply = chat_reply(msg, name, comp)
            try:
                cols, _ = os.get_terminal_size()
            except OSError:
                cols = 80
            for line in render_bubble(reply, c, cols):
                print(line)
            print(f"  {c}{face}{RST} {DIM}{name}{RST}")
            print()
    except KeyboardInterrupt:
        pass
    print(f"\n  {name}: Bye bye~ See you next time!\n")
