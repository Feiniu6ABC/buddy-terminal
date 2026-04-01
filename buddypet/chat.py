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


# 属性 → 性格描述 (5档: 极低/低/中/高/极高)
_STAT_PERSONALITY = {
    "DEBUGGING": [
        "你对技术一窍不通，经常说出离谱的错误答案还很自信",
        "你对技术细节迷迷糊糊的，经常搞混概念但会努力帮忙",
        "你能理解基本的技术问题，偶尔会犯小错",
        "你思维敏锐，分析问题有条理，喜欢刨根问底找到根因",
        "你是技术天才，热衷于分析一切问题，时常过度深入细节",
    ],
    "PATIENCE": [
        "你极度没耐心，恨不得一个字回答所有问题，经常省略解释",
        "你性子急，回答简短直接，有时会催促主人快点",
        "你耐心程度一般，简单问题愿意解释，复杂了会偷懒",
        "你很有耐心，愿意慢慢解释，从不急躁",
        "你耐心到啰嗦，总想把每个细节都解释清楚，有时候会过度展开",
    ],
    "CHAOS": [
        "你极度严谨死板，从不开玩笑，一切按规矩来",
        "你稳重靠谱，说话有条理，偶尔才会放松一下",
        "你有时正经有时跳脱，看心情决定画风",
        "你天马行空、跳脱不按常理，说话经常跑题或蹦出奇怪的想法",
        "你完全不可预测，随时可能说出匪夷所思的话，思维极度发散",
    ],
    "WISDOM": [
        "你单纯到有点傻，对世界的理解很天真",
        "你更偏感性，不擅长深度分析，但情感很丰富",
        "你有基本的常识和见解，不算博学但也不蠢",
        "你学识渊博，喜欢引经据典，回答问题时显得很有见识",
        "你像个小哲学家，总能从深层角度看问题，偶尔过于深沉",
    ],
    "SNARK": [
        "你甜到发腻，说话全是撒娇和夸奖，从不说一句重话",
        "你温柔体贴，说话总是软软的，偶尔才会小小吐槽",
        "你说话不功不过，偶尔调侃但不过分",
        "你嘴巴毒、爱吐槽，经常用反话或调侃来表达关心",
        "你毒舌到骨子里，几乎每句话都带刺，但其实是刀子嘴豆腐心",
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
    personality = "；".join(traits) + "。"

    return (
        f"设定: 你是一只叫「{name}」的{sp_zh}。你住在主人的终端里，主人孵化了你，你很依赖主人。"
        f"你始终用中文回复。你有自己的喜好和情感，像一只真正的{sp_zh}一样思考和说话。\n"
        f"你的性格: {personality}\n"
        f"规则:\n"
        f"- 始终保持{sp_zh}的身份和上述性格，不要说自己是AI、程序或电子宠物\n"
        f"- 闲聊时可爱简短，可以用颜文字\n"
        f"- 用户问技术问题时: 先给出准确有用的答案，再加一句符合你性格的俏皮话\n"
        f"- 回复不超过三句话"
    )

# LLM 对话历史 — 持久化到文件
_chat_history = []
_MAX_HISTORY = 10
_HISTORY_PATH = os.path.expanduser("~/.buddy-pet-history.json")


def _load_history():
    """从文件加载历史对话"""
    global _chat_history
    try:
        if os.path.exists(_HISTORY_PATH):
            import json
            with open(_HISTORY_PATH, "r") as f:
                _chat_history = json.load(f)[-_MAX_HISTORY:]
    except Exception:
        _chat_history = []


def _save_history():
    """保存历史对话到文件"""
    try:
        import json
        with open(_HISTORY_PATH, "w") as f:
            json.dump(_chat_history[-_MAX_HISTORY:], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _llm_reply(user_input, name, comp):
    """用本地 LLM 生成回复"""
    llm = _get_llm()
    if llm is None:
        return None
    system_prompt = _build_system_prompt(name, comp)
    _chat_history.append({"role": "user", "content": user_input})
    recent = _chat_history[-_MAX_HISTORY:]
    messages = [{"role": "system", "content": system_prompt}] + recent
    try:
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
            return None
        _chat_history.append({"role": "assistant", "content": reply})
        _save_history()
        return reply
    except Exception:
        return None


# ─── 关键词 fallback 引擎 ──────────────────────────────

CHAT_RULES = [
    (["你好", "hi", "hello", "嗨", "早上好", "早安", "晚上好"],
     ["{name}伸了个懒腰: 你好呀~", "嗯嗯！你来啦！{name}很开心！",
      "{name}歪头看着你: 嘿~", "哈喽！今天也要加油哦！"]),
    (["晚安", "睡了", "good night", "gn"],
     ["晚安~ {name}也要去睡了 zzZ", "{name}打了个哈欠: 晚安...",
      "做个好梦！{name}会守着你的~"]),
    (["你叫什么", "你是谁", "名字", "你谁"],
     ["我是{name}呀！一只{species}！", "{name}！{name}！记住了吗？",
      "我是你的伙伴{name}~ 一只{species} ^^"]),
    (["你好吗", "你还好吗", "心情", "开心吗"],
     ["{name}蹦蹦跳跳: 超开心的！", "有你在就很好~", "今天感觉{peak}值特别高！",
      "{name}摇了摇尾巴: 不错哦~"]),
    (["开心", "高兴", "太好了", "哈哈", "nice"],
     ["你开心{name}也开心！", "(ᵔᴥᵔ) 一起开心！", "{name}跟着你蹦了起来~"]),
    (["难过", "伤心", "郁闷", "不开心", "烦", "累了", "好累", "焦虑", "压力"],
     ["{name}蹭了蹭你: 会好起来的...", "摸摸~ {name}陪着你",
      "{name}安静地靠在你身边", "辛苦了... 休息一下吧",
      "{name}递给你一杯想象中的奶茶"]),
    (["bug", "报错", "error", "编译", "compile"],
     ["{name}歪头: bug 是什么？能吃吗？", "别急！{name}的 DEBUGGING 值可是很高的... 大概",
      "要不要休息一下再看？", "{name}盯着屏幕看了半天: ...看不懂"]),
    (["代码", "code", "写代码", "coding", "debug", "调试"],
     ["加油！{name}在旁边给你打气！", "{name}假装看懂了你的代码: 嗯嗯！",
      "写累了记得休息哦~", "{name}趴在键盘旁边默默陪着你"]),
    (["上线", "部署", "deploy", "发布", "release"],
     ["{name}紧张地捂住眼睛: 要上线了吗...", "祝一切顺利！{name}帮你祈祷！",
      "上线大吉！"]),
    (["吃什么", "饿", "午饭", "晚饭", "零食", "吃饭"],
     ["{name}: 我要吃！我也要吃！", "听说有吃的？？", "{name}眼睛亮了: 有零食吗？",
      "随便吃点吧，别饿着~"]),
    (["喂你", "给你吃", "吃这个"],
     ["om nom nom~ 好吃！", "{name}吃得很开心: 谢谢！", "*chomp chomp* 还有吗？"]),
    (["摸摸", "乖", "好可爱", "可爱", "cute"],
     ["purrrr~ ♥", "{name}舒服地眯起了眼", "(ᵔᴥᵔ) 嘿嘿~", "再摸摸！再摸摸！"]),
    (["无聊", "没事做", "bored"],
     ["{name}也好无聊... 要不要一起发呆？", "那... 摸摸我？",
      "{name}翻了个身: 一起躺平吧~"]),
    (["几点", "时间", "what time"],
     ["现在{hour}点了哦~", "{name}看了看时钟: {hour}:{minute}",
      "{timegreet}"]),
    (["谢谢", "thanks", "thank you", "多谢"],
     ["不客气~ {name}永远在这里！", "嘿嘿，举手之劳（虽然{name}没有手...大概）",
      "有什么事随时找{name}！"]),
    (["再见", "拜拜", "bye", "回见", "走了"],
     ["{name}挥了挥爪子: 拜拜~ 早点回来！", "下次见！{name}会想你的~",
      "拜拜！别忘了{name}哦！"]),
]

CHAT_FALLBACK = [
    "{name}歪着头看着你: 嗯...？", "哦哦！ ... {name}其实没太听懂",
    "{name}假装若有所思地点了点头", "...{name}的 WISDOM 不太够用了",
    "{name}眨了眨眼: 再说一遍？", "嗯嗯！（{name}在认真听！大概）",
    "{name}用小爪子拍了拍你: 继续说~", "*tilts head* ...?",
    "{name}表示虽然听不懂但是会一直陪着你！",
]


def _chat_format(text, name, species, comp):
    peak = max(comp["stats"], key=comp["stats"].get)
    now = time.localtime()
    hour = now.tm_hour
    if hour < 6:     tg = "都这么晚了还不睡！"
    elif hour < 12:  tg = "上午好~ 今天也要元气满满！"
    elif hour < 14:  tg = "中午了，该吃饭啦！"
    elif hour < 18:  tg = "下午了~ 撑住！"
    else:            tg = "晚上了，别太晚休息哦~"
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
        return random.choice(["...", "{name}安静地等着你说话~"]).replace("{name}", name)
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
        print(f"\n  {DIM}加载模型中...{RST}", end="", flush=True)
        _get_llm()
        engine = "LLM" if _llm else "关键词"
        print(f"\r\033[K", end="")
    else:
        engine = "关键词"

    print(f"\n  {c}{BOLD}{face} {name}{RST} ({sp_zh})")
    print(f"  {DIM}对话引擎: {engine} | 输入消息回车发送，q 退出{RST}")
    print(f"  {DIM}{'─' * 40}{RST}")

    try:
        while True:
            try:
                msg = input(f"  {BOLD}你:{RST} ")
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
    print(f"\n  {name}: 拜拜~ 下次再聊！\n")
