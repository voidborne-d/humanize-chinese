#!/usr/bin/env python3
"""
Chinese AI Text Humanizer v2.0
Transforms AI-generated Chinese text to sound more natural
Features: sentence restructuring, rhythm variation, context-aware replacement, multi-pass
"""

import sys
import re
import random
import json
import os
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Module-level flag: whether to apply noise strategies (strategies 2 & 3)
_USE_NOISE = True

# Module-level flag: whether to expand candidates with CiLin synonyms dict
# (~40K words, offline). Off by default for deterministic-ish behavior; opt-in
# via --cilin CLI flag.
_USE_CILIN = False

# Import n-gram statistical model for perplexity feedback
try:
    from ngram_model import analyze_text as ngram_analyze
except ImportError:
    try:
        from scripts.ngram_model import analyze_text as ngram_analyze
    except ImportError:
        ngram_analyze = None

# Module-level flag: whether to use stats optimization (can be toggled by CLI)
_USE_STATS = True
PATTERNS_FILE = os.path.join(SCRIPT_DIR, 'patterns_cn.json')

def load_config():
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

CONFIG = load_config()

# ─── Replacement Mappings ───

PHRASE_REPLACEMENTS = CONFIG['replacements'] if CONFIG else {
    '值得注意的是': ['注意', '要提醒的是', '特别说一下'],
    '综上所述': ['总之', '说到底', '简单讲'],
    '不难发现': ['可以看到', '很明显'],
    '总而言之': ['总之', '总的来说'],
    '与此同时': ['同时', '这时候'],
    '赋能': ['帮助', '提升', '支持'],
    '闭环': ['完整流程', '全链路'],
    '助力': ['帮助', '支持'],
}

# Regex-based replacements (key is regex pattern)
_REGEX_REPLACEMENTS = {}
PLAIN_REPLACEMENTS = {}

for key, val in PHRASE_REPLACEMENTS.items():
    # Check if key contains regex special chars suggesting it's a pattern
    if any(c in key for c in ['.*', '.+', '[', '(', '|', '\\']):
        _REGEX_REPLACEMENTS[key] = val
    else:
        PLAIN_REPLACEMENTS[key] = val

# Sort regex replacements by key length descending (longer patterns first)
REGEX_REPLACEMENTS = dict(sorted(_REGEX_REPLACEMENTS.items(), key=lambda x: len(x[0]), reverse=True))

# ─── Scene Configurations ───

SCENES = {
    'general': {
        'casualness': 0.3,
        'merge_short': True,
        'split_long': True,
        'rhythm_variation': True,
    },
    'social': {
        'casualness': 0.7,
        'merge_short': True,
        'split_long': True,
        'shorten_paragraphs': True,
        'add_casual': True,
        'rhythm_variation': True,
    },
    'tech': {
        'casualness': 0.3,
        'merge_short': True,
        'split_long': True,
        'keep_technical': True,
        'rhythm_variation': True,
    },
    'formal': {
        'casualness': 0.1,
        'merge_short': True,
        'split_long': True,
        'reduce_rhetoric': True,
        'rhythm_variation': True,
    },
    'chat': {
        'casualness': 0.8,
        'merge_short': True,
        'split_long': True,
        'shorten_paragraphs': True,
        'add_casual': True,
        'rhythm_variation': True,
    },
}

# ─── Stats-Optimized Selection ───

def pick_best_replacement(sentence, old, candidates):
    """从多个候选替换中挑选。

    Only perplexity needed for ranking — skip full analyze_text for perf.
    """
    if not _USE_STATS or not candidates or len(candidates) <= 1:
        return random.choice(candidates) if candidates else ''

    try:
        from ngram_model import compute_perplexity
    except ImportError:
        from scripts.ngram_model import compute_perplexity

    scored = []
    for candidate in candidates:
        new_sentence = sentence.replace(old, candidate, 1)
        ppl_result = compute_perplexity(new_sentence, window_size=0)
        scored.append((candidate, ppl_result.get('perplexity', 0)))

    scored.sort(key=lambda x: x[1])
    n = len(scored)
    if n <= 2:
        return scored[-1][0]
    return scored[n - 2][0]


def _compute_burstiness(text):
    """计算文本的 burstiness（困惑度变异系数），用于句式重组判断。"""
    if not _USE_STATS or not ngram_analyze:
        return None
    stats = ngram_analyze(text)
    return stats.get('burstiness', None)


# ═══════════════════════════════════════════════════════════════════
#  Strategy 1: Low-frequency bigram injection — WORD_SYNONYMS table
# ═══════════════════════════════════════════════════════════════════

WORD_SYNONYMS = {
    # ── 逻辑连接 / 转折 ──
    # Cycle 95: dropped '所以' (logic_connectors w=7 self-defeat).
    '因此': ['因而', '为此', '故而'],
    # Cycle 97: dropped '不过' from both — logic_connectors w=7 self-defeat.
    '然而': ['但', '可是', '只是'],
    # Cycle 98: dropped '然而' (logic_connectors w=7 self-defeat — replacing
    # 但是 with 然而 just trades one detected connector for another).
    '但是': ['可是', '只是'],
    '虽然': ['尽管', '即便', '就算', '纵然'],
    # Cycle 96: dropped '因此' (logic_connectors w=7 self-defeat — replacing
    # 所以 with 因此 just trades one detected connector for another).
    '所以': ['因而', '故而', '于是'],
    '而且': ['并且', '况且', '何况', '再说'],
    '或者': ['要么', '抑或', '或是', '还是'],
    '如果': ['倘若', '假如', '若是', '要是'],
    '因为': ['由于', '缘于', '出于', '鉴于'],
    '尽管': ['虽然', '即便', '纵使', '就算'],
    # ── 动词 / 行为 ──
    '能够': ['可以', '得以', '足以', '有能力'],
    '进行': ['开展', '实施', '做', '搞'],
    '实现': ['达成', '做到', '完成', '办到'],
    '提高': ['提升', '增强', '改善', '拉高'],
    # cycle 160: dropped 演进 — fixed term '发展中国家' becomes
    # '演进中国家' which reads broken (developing country, not
    # evolving). Other 发展 contexts can substitute via 推进/进展/推动.
    '发展': ['推进', '进展', '推动'],
    # '影响' removed: the idiom slot 「在 X 影响下」 is high-frequency in
    # both academic and 玄幻 register, and every candidate breaks it —
    # '波及'/'左右' are verb-only ('在...左右下' / '在...波及下' are
    # ungrammatical), '触动' is instantaneous-emotional ('在...触动下'
    # reads as 在...刺激下 but awkward), only '冲击' fits the slot. Same
    # ambiguity as the historical removals of '存在' / '有效' / '发现'.
    # cycle 160: dropped 考察 — '研究表明' commonly substituted to
    # '考察表明', which reads off-register (考察 = inspection visit).
    # Audit found in deepseek academic sample.
    # cycle 205: dropped '审视' — "本研究" → "本审视" broken
    # (审视 = critically examine, "本审视" reads as "this examination")
    '研究': ['探究', '钻研'],
    '表明': ['显示', '说明', '反映', '揭示'],
    '认为': ['觉得', '以为', '判断', '主张'],
    '需要': ['有必要', '须', '要', '得'],
    '使用': ['运用', '采用', '用', '动用'],
    '具有': ['带有', '拥有', '含有', '具备'],
    '导致': ['引发', '造成', '招致', '引起'],
    # Cycle 63: dropped '拿出' (physical/colloquial register).
    # Cycle 65: dropped '供给' — '供给' carries an economics-supply sense
    # (goods/resources), not the conceptual '提供 解释/思路/借鉴' sense.
    # Audit on 170 samples found 76 humanize-introduced 供给 cases across
    # all genres ("无法供给清晰的推理路径" / "供给代码示例" / "供给精神
    # 食粮" / "供给一面思考的镜子"). Added '给予' (grant/give) which works
    # in abstract conceptual contexts.
    '提供': ['给出', '呈上', '给予'],
    '分析': ['剖析', '解读', '拆解'],  # cycle 205: drop 审视 (same as 研究 alt)
    '促进': ['推动', '助推', '带动', '催动'],
    '利用': ['借用', '运用', '动用', '凭借'],
    '建立': ['搭建', '构筑', '组建', '创设'],
    '引起': ['招来', '激起', '触发', '挑起'],
    '采取': ['采用', '动用', '使出', '施行'],
    '包括': ['涵盖', '囊括', '含', '包含'],
    '产生': ['催生', '引出', '萌生', '冒出'],
    '增加': ['添加', '追加', '扩充', '加大'],
    '减少': ['缩减', '削减', '降低', '裁减'],
    '保持': ['维持', '守住', '留住', '持续'],
    '解决': ['化解', '处置', '破解', '攻克'],
    '改变': ['改动', '扭转', '调整', '变化'],
    '选择': ['挑选', '选定', '选用'],
    '支持': ['撑持', '扶持', '支撑'],
    '组成': ['构成', '拼成', '组合', '凑成'],
    '形成': ['催生', '铸成', '生成', '酿成'],
    '获得': ['取得', '赢得', '得到', '揽获'],
    # cycle 164: dropped '确定' — substring matches inside 确定性 (37 hits)
    # and 不确定性 (30 hits) which are technical noun terms; substitution
    # produces broken '锁定性' / '明确性' / '不敲定性' etc. Same family of
    # bug as the historical removals of '发现' / '存在' / '有效'.
    # '发现' removed: substring inside the 4-char idiom 案发现场 gets
    # corrupted into '案察觉场'/'案觉察场'/'案识破场' when the word-level
    # substitution crosses the idiom boundary. Same family of bug as '存在'
    # / '有效' below — without proper word-boundary tagging the safe move
    # is to drop the entry. Lost LR delta is small ('发现' is mostly used
    # as a finite verb where surrounding 2-char windows already vary).
    '推动': ['驱动', '助推', '催动', '拉动'],
    '加强': ['强化', '增强', '夯实', '巩固'],
    # Cycle 78: dropped '彰显' / '凸显' — both are in detect_cn's
    # ai_high_freq_words pattern (weight 6), so injecting them as humanize
    # alts for '体现' raises the AI score (self-defeating, same family
    # as cycles 76/77). Added '反映' which is a synonym in the same
    # semantic neighborhood without being an AI-flagged term.
    '体现': ['映射', '折射', '反映'],
    '满足': ['达到', '契合', '符合', '迎合'],
    # '存在' removed: substring matches across word boundaries like 留存+在
    # → 留存有 which breaks the 留存 compound. Too error-prone without
    # word-boundary awareness.
    '属于': ['归属', '算是', '属', '归入'],
    '考虑': ['斟酌', '权衡', '琢磨', '思量'],
    # cycle 164: dropped '处理' — substring matches inside 处理器 (12 hits
    # in longform corpus, technical noun); substitution produces broken
    # '处置器' / '打理器' / '应对器'. Same as 确定/发现/存在 above.
    '参与': ['加入', '介入', '参加', '投身'],
    '创造': ['缔造', '开创', '营造', '打造'],
    '描述': ['刻画', '勾勒', '叙述', '描绘'],
    '强调': ['着重', '突出', '力陈', '重申'],
    '反映': ['映射', '折射', '体现', '呈现'],
    '应用': ['运用', '采用', '使用', '施用'],
    '结合': ['融合', '配合', '糅合', '衔接'],
    '关注': ['留意', '聚焦', '在意', '着眼'],
    '涉及': ['牵涉', '关乎', '触及', '波及'],
    '依据': ['按照', '参照', '凭', '根据'],
    # Cycle 61: dropped '取用' (informal/archaic 'fetch and use').
    # Cycle 62: dropped '引用' too — '引用' means 'cite/quote/reference',
    # not 'adopt/employ'. Same audit found 27 hits where '采用' was
    # substituted with '引用' in formal contexts ("引用对抗学习" / "引用
    # 先进的5纳米制程" / "引用复式教学法") — clear semantic error: a method
    # is adopted, not cited.
    '采用': ['选用', '沿用'],
    # ── 副词 / 程度 ──
    '目前': ['眼下', '当前', '现阶段', '如今'],
    # Cycle 80: dropped '与此同时' — it is in detect_cn's mechanical_connectors
    # pattern (weight 10), so substituting '同时' with '与此同时' raises the
    # AI score (self-defeating). Pool 4→3.
    # Cycle 80 dropped '与此同时'. Cycle 94 swap '此外'/'另外'
    # (logic_connectors w=7 self-defeat) for '同样' / '一并' (clean).
    '同时': ['并且', '同样', '一并'],
    '通过': ['借助', '凭借', '经由', '依靠'],
    '根据': ['按照', '依据', '参照', '依照'],
    # '有效' removed: word is often adjectival (有效证件/有效身份/有效期),
    # and every alternative (管用/奏效/见效/起作用) is a verb/predicate that
    # breaks attributive usage (奏效身份证件). Would need word-level POS
    # tagging to handle safely.
    '基于': ['立足于', '依托', '以…为基础', '仰赖'],
    '对于': ['针对', '就', '关于', '面对'],
    '非常': ['极其', '十分', '很', '格外'],
    '已经': ['早已', '业已', '已', '早就'],
    '完全': ['彻底', '全然', '纯粹', '压根'],
    '不断': ['持续', '始终', '一再', '反复'],
    '逐渐': ['渐渐', '慢慢', '一步步', '日渐'],
    # '最要紧' alt removed: when source is '最主要', substitution gives
    # '最最要紧' (doubled-最 across word boundary).
    '主要': ['核心', '关键', '首要'],
    '一般': ['通常', '往常', '照例', '大抵'],
    '大量': ['海量', '大批', '众多', '成堆的'],
    # cycle 203: dropped '更', '再' — "更进一步" → "更更" / "更再" broken;
    # "再X" reads as repetition (wrong meaning, 进一步 implies progression).
    '进一步': ['深入', '继续'],
    '充分': ['尽情', '透彻', '淋漓', '饱满'],
    '直接': ['径直', '当面', '立刻', '干脆'],
    # cycle 164: '特别' alts trimmed to '尤其' only — '格外'/'极'/'分外'
    # all break inside 特别是 (56 hits in longform corpus, common
    # transition) producing '格外是'/'极是'/'分外是' which read as
    # ungrammatical. '尤其' is the one alt that survives the substring
    # collision: '特别是' → '尤其是' is a valid rewrite.
    '特别': ['尤其'],
    '一定': ['某种', '相当', '一些', '多少'],
    '必须': ['得', '务必', '非得', '须'],
    '可能': ['也许', '兴许', '或许', '大概'],
    # ── 名词 / 概念 ──
    # cycle 164: dropped '重要' — substring matches inside 重要性 (28 hits)
    # and 至关重要 (16 hits) and 重要性 → 核心性 / 要紧性 / 紧要性 is
    # broken (none of those are standard Chinese nouns), 至关重要 → 至关
    # 核心 also breaks the fixed idiom. The earlier '关键' alt was already
    # dropped here (cycle ~57) for doubled-关; the remaining alts have the
    # same compound-breakage bug just less visibly.
    # Cycle 60: dropped '醒目' (visually striking, not degree adverb).
    # Cycle 66: dropped '突出' too — 突出 is verb/adjective ('stick out /
    # prominent') and doesn't work as a degree adverb. Audit found 19
    # adverb-position substitutions where it produced register/semantic
    # mismatch ('突出下降' / '突出高于' / '突出提升'). Replaced with '大幅',
    # which works as adverb of degree (118 hits in human news corpus).
    # '突出' is kept in '强调' alts where it functions as V (突出重要性).
    # cycle 202: dropped '大幅' — adverb-only, "显著进展" → "大幅进展"
    # awkward (大幅 only modifies verbs of change like 提升/下降, not nouns).
    '显著': ['明显', '可观'],
    '问题': ['难题', '麻烦', '症结'],
    # cycle 203: dropped '层面' — "多方面" → "多层面" sub broken;
    # 多方面 is fixed adverb meaning "multiply", 多层面 means
    # "multi-level" (different concept). 维度/领域 still preserve adverb.
    '方面': ['维度', '领域'],
    '情况': ['状况', '形势', '境况', '局面'],
    '特点': ['特征', '属性', '标志', '特色'],
    # Cycle 71: dropped '招数' — colloquial 'trick / move' (martial-arts
    # connotation), wrong register for '方法' (systematic approach). Audit
    # found 16 humanize-introduced 招数 in news/blog ("教学招数" / "学习
    # 招数" / "教育招数论" / "工作招数" / "冲洗招数"). 招数 was already
    # blacklisted for academic, so this drop only affects general/social/
    # novel where it was firing inappropriately.
    '方法': ['办法', '手段', '途径'],
    '过程': ['历程', '进程', '流程', '经过'],
    '结果': ['成果', '产物', '结局'],
    '条件': ['前提', '条件', '要件', '门槛'],
    '作用': ['功用', '效用', '效能', '功能'],
    '内容': ['要素', '成分', '要点', '素材'],
    '程度': ['幅度', '力度', '地步', '深浅'],
    '原因': ['缘由', '根源', '起因', '来由'],
    '目标': ['目的', '指向', '靶心', '方向'],
    '水平': ['档次', '层次', '高度', '水准'],
    '范围': ['领域', '地带', '区间', '覆盖面'],
    '趋势': ['走向', '苗头', '势头', '倾向'],
    # cycle 208: dropped '实力' — "沟通能力" → "沟通实力" wrong (cycle 205
    # blocked from cilin but WORD_SYNONYMS path was missed). 实力 = strength,
    # 能力 = capability — different concepts.
    '能力': ['本事', '功底', '才干'],
    '优势': ['长处', '强项', '亮点', '好处'],
    '资源': ['物资', '储备', '要素'],
    # '场景' alt removed: when source is '市场环境', substitution gives
    # '市场场景' (doubled-场 across word boundary).
    # Cycle 79: dropped '生态' — it is in detect_cn's empty_grand_words
    # pattern (weight 12, the highest). Substituting '环境' with '生态'
    # produces AI-buzzword uses ('AI生态' / '教育生态') that the detector
    # immediately flags. Added '局面' / '情境' as clean alts in the same
    # semantic neighborhood without doubled-char boundary issues.
    '环境': ['氛围', '背景', '局面', '情境'],
    '系统': ['体系', '架构', '框架'],
    '策略': ['路线', '方案', '对策', '路子'],
}

# ═══════════════════════════════════════════════════════════════════
#  Academic-scene filters for WORD_SYNONYMS
# ═══════════════════════════════════════════════════════════════════

# Global blacklist: candidates that are themselves detected as AI patterns by
# detect_cn. Substituting INTO these is self-defeating ("环境"→"生态" triggers
# empty_grand_words; "作用"→"彰显" triggers ai_high_freq_words). Applies to all scenes.
# Kept in sync with detect_cn.py CRITICAL_PHRASES + HIGH_SIGNAL_PHRASES.
_AI_PATTERN_BLACKLIST = {
    # empty_grand_words
    '赋能', '闭环', '智慧时代', '数字化转型', '生态', '愿景', '顶层设计',
    '协同增效', '降本增效', '打通壁垒', '深度融合', '创新驱动', '全方位',
    '多维度', '系统性',
    # ai_high_freq_words
    '助力', '彰显', '凸显', '焕发', '深度剖析', '加持', '赛道', '破圈',
    '出圈', '颠覆', '革新', '底层逻辑', '抓手', '链路', '触达', '心智',
    '沉淀', '对齐', '拉通', '复盘', '迭代',
}


# Words that should NOT be substituted at all in academic context.
# These are core academic vocabulary; mechanical substitution ("研究"→"探究" etc.)
# degrades readability without reducing AIGC detection score.
ACADEMIC_PRESERVE_WORDS = {
    '研究', '分析', '发现', '指出', '表明', '认为', '显示', '揭示',
    '系统', '方法', '结果', '数据', '效果', '作用', '问题', '目标',
    '应用', '提高', '能力', '影响', '过程', '条件',
}

# Candidates that are too colloquial / archaic / informal for academic writing.
# When scene='academic', these will be filtered out of the synonym candidate pool
# before picking. If only a blacklisted candidate remains, the original word is kept.
ACADEMIC_BLACKLIST_CANDIDATES = {
    # 动词 - 过于口语或古语
    '施用', '拉高', '搞', '弄', '整', '做', '做过', '搞定', '摆平',
    '挑', '琢磨', '思量', '打理', '料理', '撑持', '揽获', '敲定',
    '识破', '觉察', '察觉', '看出', '拆解', '宛若',
    # 名词/形容词 - 口语化
    '本事', '家底', '本钱', '档次', '段位', '地带', '招数', '打法',
    '麻烦', '症结', '亮点', '好处', '苗头', '势头', '门槛',
    '成堆的', '最要紧的', '海量',
    # 程度词 - 口语
    '压根', '干脆', '径直', '当面', '兴许', '估摸着', '约莫', '大抵',
    '早就', '业已',
    # 架构/框架 对 "系统" - 过于泛化
    '架构', '框架',
    # 探究/剖析/审视 对 "研究/分析" - 虽然偶尔可用但大规模替换破坏学术调性
    '探究', '剖析',
    # 连接词口语化
    '缘于', '缘由', '来由',
    # 因果/序列连词 - 在 academic 里 '于是' 倾向 sequential temporal sense
    # ('then …'), 不像 '因此 / 因而' 那样表示 logical inference. Cycle 64
    # audit found 12 academic samples with '于是 解释 / 于是 削弱 / 于是
    # 及时干预' 等 logical 上下文里被误用. 保留给 general/novel scene.
    '于是',
}


# Novel/fiction register: a subset of ACADEMIC_BLACKLIST_CANDIDATES still
# applies to 3rd-person 玄幻/武侠/小说 prose, but several entries are
# narrative-friendly verbs ('察觉'/'识破') that academic writing rejects yet
# read naturally in fiction. Carve those out so novel mode keeps useful
# perplexity-boosting substitutes while still stripping colloquial ones
# ('搞'/'拉高'/'业已') that break narrative register.
NOVEL_BLACKLIST_CANDIDATES = ACADEMIC_BLACKLIST_CANDIDATES - {
    # Action/perception verbs that fiction uses freely
    '觉察', '察觉', '识破', '看出', '拆解',
    # 海量/眼下 are 武侠/玄幻 idioms ("海量灵气" / "眼下危机")
    '海量', '眼下',
    # 古风 register friendly
    '宛若',
    # Investigation verbs OK in narrative ("探究秘境奥秘")
    '探究', '剖析',
}


def _filter_candidates_for_scene(word, candidates, scene):
    """过滤不适合场景的候选词。返回过滤后的列表，若全被过滤则返回原列表。

    Always filters _AI_PATTERN_BLACKLIST (candidates that trigger detect_cn itself).
    Additionally filters ACADEMIC_BLACKLIST_CANDIDATES when scene='academic',
    or NOVEL_BLACKLIST_CANDIDATES when scene='novel'.
    """
    filtered = [c for c in candidates if c not in _AI_PATTERN_BLACKLIST]
    if scene == 'academic':
        filtered = [c for c in filtered if c not in ACADEMIC_BLACKLIST_CANDIDATES]
    elif scene == 'novel':
        filtered = [c for c in filtered if c not in NOVEL_BLACKLIST_CANDIDATES]
    return filtered if filtered else candidates


# ═══════════════════════════════════════════════════════════════════
#  CiLin (哈工大同义词词林扩展版) - optional expansion
# ═══════════════════════════════════════════════════════════════════

_CILIN_CACHE = None
_CILIN_FILE = os.path.join(SCRIPT_DIR, 'cilin_synonyms.json')

# Curated blacklist of CiLin candidates that are archaic, domain-mismatched,
# or POS-mismatched for common Chinese words. CiLin's "synonym" relation is
# taxonomic (not substitutable), so these slip through — manually filtered
# from spot-checks on 应用/发展/重要/系统/分析/提高/使用.
_CILIN_BLACKLIST = {
    # Archaic / 文言 — "conscript/order-around" tone for 使用/应用
    '使唤', '使役', '役使', '差遣', '驱使',
    # Mismatched POS (noun / noun-phrase for adjective 重要)
    '严重性', '要紧性', '关键性', '基本点', '国本',
    # Domain-mismatched (upward-numerical for 发展)
    '上扬', '上移', '上进', '升华',
    # Archaic / classical for 系统
    '板眼', '伦次', '条贯', '战线',
    # Overly colloquial / butcher-y for 分析
    '剖解', '解构',
    # Redundant / unnatural
    '显要', '要害', '紧要',
    # cycle 150 quality audit additions —— cilin synonyms that broke
    # semantics in real bn=10 humanize output across academic / novel
    # / review samples. each entry: source word → bad synonym observed.
    # Poetic / descriptive for 最高 ("highest" — quantitative)
    '万丈', '亭亭', '凌云', '参天', '摩天', '高高的',
    # Wrong scale / register for 团队 ("team")
    '团伙', '集团',
    # Technical / wrong-POS for 核心 ("core")
    '主从', '为主',
    # Assembly / event mismatch for 会议 ("meeting")
    '集会',
    # Specific-context for 完成 ("complete")
    '交卷', '到位', '姣好', '完了', '完事',
    # Wrong meaning for 问题 ("problem/issue")
    '主焦点', '事端', '关节', '关子',
    # Wrong meaning for 进行 ("conduct")
    '前进', '行进',
    # POS / meaning mismatch found in cycle 150 quality audit
    '容许',  # replaces 可能 — verb instead of modal
    '呈上',  # replaces 提供 — overly formal "submit upward"
    # cycle 186: cilin 领域 alts that mean physical land, wrong for
    # abstract domain — 教育领域 → 教育土地/园地/国土/圈子/天地 broken
    '土地', '园地', '国土', '圈子', '天地',
    # cycle 195: broken alts surfaced in README humanize 输出 audit
    '念书',  # 学习 alt — "深度学习" → "深度念书" semantically wrong
    '攻读',  # 学习 alt — only "study academically", off in "深度学习"
    '学学',  # 学习 alt — broken (just repeated char)
    '修业',  # 学习 alt — archaic ("study at school")
    '上学',  # 学习 alt — only "go to school", off in tech contexts
    '就学',  # 学习 alt — same as 上学
    '肥力',  # 精力 alt — 肥力 means soil fertility (土壤肥力)
    '个私',  # 个人 alt — regional/dialect, off in formal text
    '人家',  # 个人 alt — pronoun "she/he/they", semantic shift
    '匹夫',  # 个人 alt — archaic "common person"
    '一发',  # 更加 alt — archaic, "一发充实" reads broken
    '事体',  # 工作/事情 alt — regional dialect, off in formal text
    '本性',  # 个性 alt — "个性化" → "本性化" broken (本性 ≈ nature)
    '天性',  # 个性 alt — "个性化" → "天性化" broken
    '生性',  # 个性 alt — "个性化" → "生性化" broken
    '秉性',  # 个性 alt — same broken pattern
    '赋性',  # 个性 alt — same broken pattern
    '擘画',  # 规划/计划 alt — archaic, off in modern Chinese
    '宏图',  # 规划/计划 alt — "任务规划" → "任务宏图" wrong (宏图 = grand vision)
    '圈圈',  # 层面/局面/范畴 alt — wrong meaning ("circle")
    '框框',  # 层面/范畴 alt — wrong meaning ("frame")
    '局面',  # 层面 alt — "各个层面" → "各个局面" awkward
    '对头',  # 正确/科学 alt — colloquial "correct/foe", semantic shift
    '不利',  # 正确/科学 alt — opposite meaning ("unfavorable")!
    '不易',  # 正确/科学 alt — unrelated ("not easy")
    '得法',  # 正确/科学 alt — narrow ("appropriate method")
    '上头',  # 方面 alt — body part ("top of head")
    '恰切',  # 适应 alt — "自适应" → "自恰切" broken
    '出发点',  # 角度 alt — "从角度" → "从出发点" register-narrow
    '动用',  # 应用/使用 alt — "应用" → "动用" implies mobilizing resources
    '深浅',  # 深度 alt — "深度学习" → "深浅学习" broken
    '纵深',  # 深度 alt — military register, off
    '穿越',  # 通过 alt — "通过" → "穿越" wrong (穿越 = traverse)
    '穿过',  # 通过 alt — same wrong meaning
    '越过',  # 通过 alt — same wrong meaning
    '适于',  # 适应 alt — "自适应" → "自适于" broken
    '升任',  # 提升 alt — only "promote in rank"
    '升官',  # 提升 alt — same job-promotion narrow
    '升迁',  # 提升 alt — same job-promotion narrow
    '提干',  # 提升 alt — same, military/cadre register
    '咱家',  # 个人 alt — colloquial regional ("us/me"), wrong meaning
    '助长',  # 推动 alt — implies negative ("AI 推动教育" → "AI 助长教育" wrong, 助长 = abet/encourage-bad)
    '事理',  # 道理 alt — archaic register, off in modern Chinese
    '理路',  # 道理 alt — same archaic
    '所以然',  # 道理 alt — too philosophical, off in modern Chinese
    '技巧',  # 技术 alt — narrow "skill", off in tech contexts
    '招术',  # 技术 alt — wuxia register, very off
    '规模',  # 层面/范畴 alt — wrong dimension ("scale" not "aspect")
    '升格',  # 提升 alt — "upgrade to higher class", off in skill/effort contexts
    '升级',  # 提升 alt — software/version register, off in many contexts
    '数目字',  # 数字 alt — "数字化" → "数目字化" broken (数目字 = numerical figure)
    # cycle 203 (sway 语句通顺优先 directive): more broken alts surfaced
    '兼具',  # 具有 alt — narrow "include both", "兼具广阔前景" broken
    '由此',  # 通过 alt — connector word, "由此各方合力" broken (loses 通过 means "via")
    '稿子',  # 规划/计划 alt — colloquial "draft", off in formal "任务稿子"
    '不错',  # 科学 alt — informal compliment, "践行不错的时间管理" broken
    '正值',  # 正在 alt — only with time periods (正值春季), broken in "正值推动"
    '条理',  # 系统 alt — "智能评估系统" → "智能评估条理" broken (条理 = orderliness)
    '功用',  # 意义/作用 alt — narrow "function", "意义" → "功用" register-mismatched
    # cycle 205 (sway 语义不通畅 directive 续):
    '世界',  # 领域 alt — "教育领域" → "教育世界" semantic shift (世界 = world)
    '实力',  # 能力 alt — "沟通能力" → "沟通实力" wrong (能力 = capability, 实力 = strength)
    '体系',  # 系统 alt — "智能评估系统" → "智能评估体系" register-mismatched
    '审美',  # 审视 alt — "审视" → "审美" totally wrong meaning (aesthetic judgment)
    '琢磨',  # 研究 alt — informal "ponder", off in formal contexts
    '作用',  # 意义 alt — "真正意义上" → "真正作用上" broken (作用 = function, 意义 = meaning/significance)
    '力量',  # 意义/能力 alt — "真正意义上" → "真正力量上" broken
    '功力',  # 意义 alt — "真正意义上" → "真正功力上" broken (功力 = 内力 wuxia)
    '功效',  # 意义 alt — "真正意义上" → "真正功效上" broken
    '功能',  # 意义 alt — "真正意义上" → "真正功能上" broken (function not meaning)
    '今朝',  # 现在 alt — archaic poetic register ("今朝有酒今朝醉"), off in modern prose
    '目下',  # 目前 alt — archaic ("at present" classical Chinese), sway flagged msg 2198
    '手上',  # 目前 alt — colloquial "in hand", off in formal/academic
    '时下',  # 目前 alt — narrow ("nowadays" trend-context), off in research register
    # cycle 208 (sway 整理 README sweep):
    '于今',  # 现在 alt — archaic, "于今" 不像现代汉语
    '今日',  # 现在 alt — slightly poetic, off in modern prose ("今日X" 报纸 register)
    '今昔',  # 现在 alt — comparative "now and then", different meaning
    '参酌',  # 研究 alt — archaic "consult and consider", off in modern formal
    '掂量',  # 研究 alt — colloquial "weigh up"
    '揣摩',  # 研究 alt — narrow "ponder/figure out"
    '斟酌',  # 研究 alt — narrow "deliberate carefully", off in technical research
    '切磋',  # 研究 alt — narrow "exchange skills" (martial arts/scholarly)
    '技艺',  # 技术 alt — narrow "art/craft", off in tech contexts
    '技能',  # 技术 alt — narrow "skill", off when 技术 means "technology"
    '反过来看',  # noise/transition alt — odd opener mid-essay
    '说到这里',  # noise/transition alt — narrative voice, off in essay
    '人为',  # 人工 alt — "人工智能" → "人为智能" broken (人为=man-made, conceptually different)
    '人造',  # 人工 alt — same; "人造智能" reads as "fake AI"
    '力士',  # 人工 alt — totally different ("strongman")
    '人力',  # 人工 alt — "人工智能" → "人力智能" broken (人力 = manpower)
    '教养',  # 教育 alt — "教育教学" → "教养教学" broken (教养=upbringing/manners)
    '教化',  # 教育 alt — moralistic tone, off in modern AI/tech context
    '感化',  # 教育 alt — moralistic, off
    '启蒙',  # 教育 alt — narrow ("enlighten" beginner level)
    '教诲',  # 教育 alt — moralistic ("teaching/admonition"), off
    '教导',  # 教育 alt — narrow ("guide/instruct"), off in 教育领域
    '力促',  # 推动 alt — archaic ("forcefully promote")
    '末了',  # 最后 alt — colloquial dialect
    '末后',  # 最后 alt — archaic
    '末尾',  # 最后 alt — physical position, off in temporal context
    '尾子',  # 最后 alt — colloquial
    '尾声',  # 最后 alt — narrow ("finale" of event/work)
}


# Source-side blacklist: 2-char cilin keys whose substitution produces
# broken Chinese — either because they're almost always part of longer
# compounds (substring-collision) or because their cilin alts shift
# meaning even in standalone position. Block at the source (skip these
# as replacement targets in reduce_cross_para_3gram_repeat).
#
# cycle 191: '不了' — X不了 negative-potential compound (受不了/少不了/
# 免不了/做不了…), 不了 → 不息/不停 breaks compound (少不息).
# cycle 192: empirical audit of 10 high-freq function words. Each line
# below = source word + the broken sample observed in test:
_CILIN_SOURCE_BLACKLIST = {
    '不了',  # 少不了 → 少不息
    '不是',  # 不是教师 → 纰缪教师 (alts: 不对/偏向/纰缪 — meaning shift)
    '一下',  # 想一下 → 想一瞬 (alts 一刹那/一瞬 too dramatic)
    '一些',  # 带一些礼物 → 带好几礼物 (好几 needs 个 measure word)
    '不要',  # 不要担心 → 并非担心 (并非 is statement-of-fact, not directive)
    '就是',  # 就是这样 → 即使这样 (即使 = "even if", needs main clause)
    '不能',  # 不能解决 → 未能解决 ("can't" → "didn't succeed", semantic shift)
    '什么',  # 什么东西 → 咋样东西 (咋样 colloquial + register-mismatch)
    '只是',  # 只是开始 → 单单开始 (单单 modifies things, not actions)
}


def _load_cilin():
    """Lazy-load filtered CiLin synonyms. Returns dict[word] -> list[candidate] or empty dict."""
    global _CILIN_CACHE
    if _CILIN_CACHE is not None:
        return _CILIN_CACHE
    if not os.path.exists(_CILIN_FILE):
        _CILIN_CACHE = {}
        return _CILIN_CACHE
    try:
        with open(_CILIN_FILE, 'r', encoding='utf-8') as f:
            _CILIN_CACHE = json.load(f)
    except (json.JSONDecodeError, OSError):
        _CILIN_CACHE = {}
    return _CILIN_CACHE


def expand_with_cilin(word, candidates, scene='general'):
    """Expand a candidate list with CiLin synonyms (filtered through blacklists).

    Only used when enabled via --cilin CLI flag. CiLin has ~40K words vs the
    hand-curated ~200 in WORD_SYNONYMS, so expansion gives much more variety —
    but CiLin's "synonym" relation is loose (taxonomic, not strictly substitutable)
    and contains archaic/idiomatic candidates. Always filter through scene blacklist.
    """
    cilin = _load_cilin()
    extras = cilin.get(word, [])
    if not extras:
        return candidates
    existing = set(candidates)
    filtered = []
    for c in extras:
        if c in existing:
            continue
        if c in _AI_PATTERN_BLACKLIST:
            continue
        if c in _CILIN_BLACKLIST:
            continue  # semantic/POS/register mismatch, curated
        if scene == 'academic' and c in ACADEMIC_BLACKLIST_CANDIDATES:
            continue
        if scene == 'novel' and c in NOVEL_BLACKLIST_CANDIDATES:
            continue
        filtered.append(c)
        existing.add(c)
    return list(candidates) + filtered


# ═══════════════════════════════════════════════════════════════════
#  Strategy 3: Noise expression injection — expression table
# ═══════════════════════════════════════════════════════════════════

NOISE_EXPRESSIONS = {
    'hedging': ['说实话', '坦白讲', '客观地说', '实事求是地讲', '平心而论',
                '老实说', '不夸张地说', '公正地看'],
    'self_correction': ['或者说', '准确地讲', '换个角度看', '严格来说',
                        '更确切地说', '往深了讲', '细想一下'],
    # cycle 183 dropped '或许' — in detect_cn HEDGING_PHRASES, injection
    # increases hedging_language count, self-defeat (cycle 77 family).
    'uncertainty': ['大概', '差不多', '似乎', '多少有些',
                    '约莫', '估摸着', '八成'],
    # Cycle 77: dropped '换句话说' — it is in detect_cn's ai_high_freq_words
    # pattern, so injecting it raises the AI score (self-defeating).
    # cycle 208: trimmed — '话说回来'/'反过来看'/'说到这里'/'回过头看' all
    # narrative-voice openers that read as off-register in essay/factual text.
    # Kept '再往下想'/'顺着这个思路' which work in analytical contexts.
    'transition_casual': ['再往下想', '顺着这个思路'],
    # cycle 195: trimmed 8 → 3 — removed register-mismatched fillers
    # (怎么说呢/不瞒你说/你别说/讲真/这么说吧) that read very colloquial /
    # internet-slangy. They land in formal/business/academic text and
    # break fluency. Kept '其实/说到底/当然了' which fit most registers.
    'filler': ['当然了', '其实', '说到底'],
    # Cycle 55: dropped 5 entries that appear 0 times in 2.5M chars of
    # human Chinese (news + novel corpora) — '依我之见 / 以我的经验 /
    # 在我的理解里 / 就我所知 / 我个人倾向于'. These read as AI-style
    # stilted hedges in any register (academic / general / social), not
    # just academic. '我觉得' and '在我看来' kept (105 + 4 hits in human
    # corpus, idiomatic).
    'personal': ['我觉得', '在我看来'],
}

# Academic-safe categories (no oral fillers or personal opinions)
NOISE_ACADEMIC_CATEGORIES = ['hedging', 'self_correction', 'uncertainty']
# Academic-specific hedging (more formal)
NOISE_ACADEMIC_EXPRESSIONS = {
    # cycle 157: pool expanded from 4 → 7 each. Cycle 154 bn=10 academic
    # dropped from +15 (with casual-filler injection) to +10.5 (with this
    # formal-only pool). More formal candidates give random.choice more
    # variety, raising the chance of hitting LR-favorable phrasing.
    'hedging': ['客观地说', '实事求是地讲', '平心而论', '公正地看',
                '从客观角度看', '理性而言', '客观看待'],
    'self_correction': ['准确地讲', '严格来说', '更确切地说', '往深了讲',
                        '细究而论', '准确而言', '严谨地说'],
    # Cycle 77: dropped '在一定程度上' from this academic uncertainty pool too
    # (sister fix to cycle 76 in academic_cn). It is in detect_cn's hedging_
    # language and ai_high_freq_words patterns; injecting it raises the AI
    # score. Pool 5→4.
    # cycle 183 dropped '或许' from academic uncertainty too — sister
    # fix to general pool. Same detect_cn HEDGING_PHRASES self-defeat.
    'uncertainty': ['大致', '似乎', '多少',
                    '大体', '约莫', '大体上'],
}

def _load_bigram_freq():
    """Load bigram frequencies from the n-gram frequency table."""
    try:
        from ngram_model import _load_freq
    except ImportError:
        try:
            from scripts.ngram_model import _load_freq
        except ImportError:
            return {}
    freq = _load_freq()
    return freq.get('bigrams', {})


def reduce_high_freq_bigrams(text, strength=0.3, scene='general'):
    """
    策略1: 扫描文本中的高频 bigram，尝试用低频同义替换降低可预测性。
    strength: 0-1，控制替换比例。
    scene: 'general' / 'academic' / 'social' —
      - academic: 跳过 ACADEMIC_PRESERVE_WORDS，候选过 ACADEMIC_BLACKLIST_CANDIDATES

    使用基于词的替换（非位置），避免长度变化导致的错位问题。
    """
    bigram_freq = _load_bigram_freq()
    if not bigram_freq:
        return _simple_synonym_pass(text, strength, scene=scene)

    chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chars) < 4:
        return text

    preserve = ACADEMIC_PRESERVE_WORDS if scene == 'academic' else set()

    # Step 1: Score each WORD_SYNONYMS word by its surrounding bigram frequency
    word_scores = []  # (word, total_bigram_freq, count_in_text)
    for word in WORD_SYNONYMS:
        if word in preserve:
            continue
        count = text.count(word)
        if count == 0:
            continue
        # Compute bigram frequency of this word's characters
        word_chars = re.findall(r'[\u4e00-\u9fff]', word)
        total_freq = 0
        for i in range(len(word_chars) - 1):
            bg = word_chars[i] + word_chars[i + 1]
            total_freq += bigram_freq.get(bg, 0)
        word_scores.append((word, total_freq, count))

    if not word_scores:
        return text

    # Step 2: Sort by bigram frequency (highest first)
    word_scores.sort(key=lambda x: x[1], reverse=True)

    # Step 3: Replace top N unique words (controlled by strength)
    n_replace = max(1, int(len(word_scores) * strength))
    replaced_words = set()

    for word, freq_score, count in word_scores[:n_replace]:
        if word in replaced_words:
            continue

        candidates = _filter_candidates_for_scene(word, WORD_SYNONYMS[word], scene)
        if _USE_CILIN:
            candidates = expand_with_cilin(word, candidates, scene)

        # Rank candidates by bigram frequency ascending (rarest first)
        ranked = []
        for candidate in candidates:
            cand_chars = re.findall(r'[\u4e00-\u9fff]', candidate)
            if not cand_chars:
                continue
            total_f = 0
            for i in range(len(cand_chars) - 1):
                total_f += bigram_freq.get(cand_chars[i] + cand_chars[i + 1], 0)
            ranked.append((candidate, total_f))
        if not ranked:
            continue
        ranked.sort(key=lambda x: x[1])

        # Pick strategy: NOT the rarest (too weird, e.g. 施用/拉高/本事),
        # but moderately rare — lower third by bigram frequency when possible.
        n_cand = len(ranked)
        if n_cand == 1:
            primary = ranked[0][0]
        elif n_cand == 2:
            primary = ranked[0][0]
        else:
            idx = min(max(1, n_cand // 3), n_cand - 2)
            primary = ranked[idx][0]

        # Partial replacement: don't replace EVERY occurrence of the word.
        # Replacing all creates NEW AI-pattern repetition (e.g. "系统"×6 → "架构"×6).
        # Keep some original occurrences + mix in alternative candidates for variation.
        SENTINEL = '\x00'

        def _protect(w):
            return SENTINEL.join(w) if len(w) > 1 else w

        occurrences = [m.start() for m in re.finditer(re.escape(word), text)]
        if not occurrences:
            continue
        # Replace ~60% of occurrences (min 1, always at least the first)
        n_replace_occ = max(1, int(len(occurrences) * 0.6))
        # Randomly select which occurrences to replace (deterministic via current seed)
        to_replace = set(random.sample(range(len(occurrences)), n_replace_occ))

        # Pick alternative candidates for variety when multiple occurrences replaced
        # (avoid monotone repetition of single replacement)
        alt_candidates = [c for c, _ in ranked if c != primary] or [primary]

        # Capture original text for next-char lookups (text mutates inside loop)
        original_text = text
        ranked_alts = [c for c, _ in ranked]

        def _pick_safe(default, next_ch):
            """Avoid alts whose last char equals next_ch (would double).
            Falls back to default if no safe alt exists."""
            if not next_ch or default[-1:] != next_ch:
                return default
            for cand in ranked_alts:
                if cand and cand[-1] != next_ch:
                    return cand
            return default

        # Rebuild text by iterating occurrences back-to-front (avoid shifting positions)
        for k in reversed(range(len(occurrences))):
            pos = occurrences[k]
            if k not in to_replace:
                continue
            # Word-boundary doubling guard: check next char in source after the
            # word being replaced. If alt ends with that char, swap to a
            # non-doubling alt. Catches '能够以X' → '可以以X' / '系统的研究'
            # → '架构的的' family of bugs without removing the entry entirely.
            next_ch = original_text[pos + len(word):pos + len(word) + 1]
            # Cycle 54: left-context cross-boundary guard. '解决' inside
            # '了解决策' actually spans 了解|决策 (two distinct words);
            # replacing 解决 with 攻克 corrupts to '了攻克策'. Skip when
            # the word's leading char + prev char form a known 2-char word
            # AND the word's trailing char + next char also form a 2-char
            # word — that's the cross-boundary signature.
            prev_ch = original_text[pos - 1:pos] if pos > 0 else ''
            if word == '解决' and prev_ch == '了' and next_ch in '策心议定断':
                continue
            # Pick primary for first replaced occurrence, alternate for others
            if k == min(to_replace):
                replacement = _pick_safe(primary, next_ch)
            else:
                pick = random.choice([primary] + alt_candidates)
                replacement = _pick_safe(pick, next_ch)
            protected = _protect(replacement)
            text = text[:pos] + protected + text[pos + len(word):]

        replaced_words.add(word)

        # Also mark synonyms of the same word to avoid replacing the replacement
        for syn in candidates:
            if syn != primary and syn in WORD_SYNONYMS:
                replaced_words.add(syn)

    # Strip sentinels
    text = text.replace('\x00', '')

    return text


def _simple_synonym_pass(text, strength=0.3, scene='general'):
    """Fallback: replace a fraction of WORD_SYNONYMS matches randomly.

    scene: 'academic' filters PRESERVE words and BLACKLIST candidates.
    """
    preserve = ACADEMIC_PRESERVE_WORDS if scene == 'academic' else set()
    found = []
    for word in WORD_SYNONYMS:
        if word in preserve:
            continue
        start = 0
        while True:
            pos = text.find(word, start)
            if pos < 0:
                break
            found.append((word, pos))
            start = pos + len(word)
    if not found:
        return text
    n_replace = max(1, int(len(found) * strength))
    random.shuffle(found)
    replaced_positions = set()
    for word, pos in found[:n_replace]:
        if any(p in replaced_positions for p in range(pos, pos + len(word))):
            continue
        candidates = _filter_candidates_for_scene(word, WORD_SYNONYMS[word], scene)
        if not candidates:
            continue
        candidate = random.choice(candidates)
        text = text[:pos] + candidate + text[pos + len(word):]
        for p in range(pos, pos + len(candidate)):
            replaced_positions.add(p)
    return text


# ═══════════════════════════════════════════════════════════════════
#  Strategy 2: Sentence length randomization
# ═══════════════════════════════════════════════════════════════════

_PARA_BOOST_ATTRIBUTION = (
    '指出', '表明', '认为', '揭示', '发现', '显示', '提出',
    '说', '称', '讲', '强调', '主张', '断言',
)
_PARA_BOOST_SUBORDINATE = (
    '随着', '鉴于', '为了', '由于', '尽管', '虽然',
    '如果', '假如', '若是', '倘若', '要是', '即便', '纵然',
    '除了', '除非', '只要', '只有', '无论', '不管',
    '当', '每当', '一旦',
)
_PARA_BOOST_BARE_CONTINUATOR = (
    '使得', '使', '导致', '引起', '造成', '致使',
)


def _boost_one_paragraph_cv(para, target_cv):
    """Truncate the longest sentence at first comma if paragraph-internal
    sentence-length CV is below target. Reuses guards from
    randomize_sentence_lengths Strategy B."""
    cn_count = len(re.findall(r'[一-鿿]', para))
    if cn_count < 60:
        return para

    parts = re.split(r'([。！？])', para)
    pairs = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i]
        p = parts[i + 1] if i + 1 < len(parts) else ''
        if s.strip():
            pairs.append([s, p])
    if len(parts) % 2 == 1 and parts[-1].strip():
        pairs.append([parts[-1], ''])

    if len(pairs) < 3:
        return para

    lens = [len(re.findall(r'[一-鿿]', s)) for s, _ in pairs]
    valid = [(i, l) for i, l in enumerate(lens) if l >= 5]
    if len(valid) < 3:
        return para
    vl = [l for _, l in valid]
    m = sum(vl) / len(vl)
    if m == 0:
        return para
    var = sum((l - m) ** 2 for l in vl) / len(vl)
    cv = (var ** 0.5) / m

    if cv >= target_cv:
        return para

    long_idx = max(range(len(pairs)), key=lambda i: lens[i])
    long_s, long_p = pairs[long_idx]
    if lens[long_idx] < 18:
        return para

    comma_pos = long_s.find('，')
    if comma_pos < 0:
        return para
    first_part = long_s[:comma_pos]
    rest_part = long_s[comma_pos + 1:]
    if (len(re.findall(r'[一-鿿]', first_part)) < 8 or
            len(re.findall(r'[一-鿿]', rest_part)) < 8):
        return para

    first_stripped = first_part.lstrip()
    last_nl = first_part.rfind('\n')
    if last_nl >= 0:
        tail_cn = len(re.findall(r'[一-鿿]',
                                 first_part[last_nl + 1:]))
        if tail_cn < 3:
            return para

    if first_part.endswith(_PARA_BOOST_ATTRIBUTION):
        return para
    if first_stripped.startswith(_PARA_BOOST_SUBORDINATE):
        return para
    if rest_part.lstrip().startswith(_PARA_BOOST_BARE_CONTINUATOR):
        return para

    pairs[long_idx] = [first_part, '。']
    pairs.insert(long_idx + 1, [rest_part, long_p or '。'])
    return ''.join(s + p for s, p in pairs)


_PARA_BOOST_REACTIONS = (
    '的确', '确实如此', '颇有道理', '不无道理',
    '有一定道理', '各有道理', '各有说法', '值得深思',
)


def _boost_one_para_via_merge(para, target_cv):
    """Merge a single pair of adjacent short-medium sentences with a comma
    to lift a uniform paragraph's internal sentence-length CV. Reuses the
    Strategy-A merge guards from randomize_sentence_lengths (reactions,
    paragraph-break boundary, total length cap)."""
    cn_count = len(re.findall(r'[一-鿿]', para))
    if cn_count < 60:
        return para

    parts = re.split(r'([。！？])', para)
    pairs = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i]
        p = parts[i + 1] if i + 1 < len(parts) else ''
        if s.strip():
            pairs.append([s, p])
    if len(parts) % 2 == 1 and parts[-1].strip():
        pairs.append([parts[-1], ''])

    if len(pairs) < 4:
        return para

    lens = [len(re.findall(r'[一-鿿]', s)) for s, _ in pairs]
    valid = [l for l in lens if l >= 5]
    if len(valid) < 3:
        return para
    m = sum(valid) / len(valid)
    if m == 0:
        return para
    var = sum((l - m) ** 2 for l in valid) / len(valid)
    cv = (var ** 0.5) / m

    if cv >= target_cv:
        return para

    # Find an adjacent pair both 5..25 chars whose merged length is <=60
    # (so we cross the medium→long boundary and lift CV without making
    # the merged sentence unwieldy).
    for i in range(len(pairs) - 1):
        l1, l2 = lens[i], lens[i + 1]
        if not (5 <= l1 <= 25 and 5 <= l2 <= 25):
            continue
        if l1 + l2 > 60:
            continue
        s1, _ = pairs[i]
        s2, p2 = pairs[i + 1]
        if (s1.strip() in _PARA_BOOST_REACTIONS or
                s2.strip() in _PARA_BOOST_REACTIONS):
            continue
        if '\n' in s2:
            continue
        merged = s1.rstrip() + '，' + s2.lstrip()
        pairs[i] = [merged, p2]
        pairs.pop(i + 1)
        break

    return ''.join(s + p for s, p in pairs)


def reduce_cross_para_3gram_repeat(text, max_replacements=4, scene='general',
                                   style=None, seed=None):
    """v5 P1.3 humanize counter-measure for cross_para_3gram_repeat
    (LR coef +2.24 on longform).

    Walks paragraphs, identifies 2-char words (CiLin keys) that appear
    in 2+ paragraphs, and replaces ONE occurrence in a later paragraph
    with a CiLin synonym. Replacing a 2-char word breaks two
    overlapping 3-grams, so even a handful of substitutions measurably
    drops the cross-paragraph trigram repetition ratio.

    Scene-aware via the same blacklists as expand_with_cilin
    (_AI_PATTERN_BLACKLIST / _CILIN_BLACKLIST / ACADEMIC_BLACKLIST_CANDIDATES
    / NOVEL_BLACKLIST_CANDIDATES). Skips when the scene/style filters
    yield no usable synonym.

    Prefers words in exactly 2 paragraphs (each replacement directly
    drops a repeat — words spanning 3+ paragraphs need more sub work
    to clear).
    """
    if seed is not None:
        random.seed(seed)

    cilin = _load_cilin()
    if not cilin:
        return text

    paragraphs = text.split('\n\n')
    if len(paragraphs) < 3:
        return text

    cilin_keys = set(cilin.keys()) - _CILIN_SOURCE_BLACKLIST
    para_words = []
    for p in paragraphs:
        chars = re.findall(r'[一-鿿]', p)
        words_in_p = set()
        for i in range(len(chars) - 1):
            w = chars[i] + chars[i + 1]
            if w in cilin_keys:
                words_in_p.add(w)
        para_words.append(words_in_p)

    word_paras = {}
    for i, words in enumerate(para_words):
        for w in words:
            word_paras.setdefault(w, []).append(i)

    candidates = [(w, ps) for w, ps in word_paras.items() if len(ps) >= 2]
    if not candidates:
        return text

    # Prefer words appearing in fewer paragraphs (each replacement
    # there directly clears the repeat). Then random within tier.
    candidates.sort(key=lambda x: len(x[1]))
    # Shuffle within each tier of equal paragraph-count
    tier_buckets = {}
    for w, ps in candidates:
        tier_buckets.setdefault(len(ps), []).append((w, ps))
    for k in tier_buckets:
        random.shuffle(tier_buckets[k])
    ordered = []
    for k in sorted(tier_buckets):
        ordered.extend(tier_buckets[k])

    new_paragraphs = list(paragraphs)
    replaced = 0

    for word, para_indices in ordered:
        if replaced >= max_replacements:
            break
        synonyms = cilin.get(word, [])
        if not synonyms:
            continue
        filtered = []
        for c in synonyms:
            if c in _AI_PATTERN_BLACKLIST:
                continue
            if c in _CILIN_BLACKLIST:
                continue
            if scene == 'academic' and c in ACADEMIC_BLACKLIST_CANDIDATES:
                continue
            if (scene == 'novel' or style == 'novel') and \
                    c in NOVEL_BLACKLIST_CANDIDATES:
                continue
            filtered.append(c)
        if not filtered:
            continue
        synonym = random.choice(filtered)
        # Replace in the LAST occurrence paragraph (so the established
        # term lands in earlier paragraphs and the variation shows up
        # later — closer to how humans drift).
        last_idx = para_indices[-1]
        new_para = new_paragraphs[last_idx].replace(word, synonym, 1)
        if new_para != new_paragraphs[last_idx]:
            new_paragraphs[last_idx] = new_para
            replaced += 1

    return '\n\n'.join(new_paragraphs)


_PARA_INTERJECTION_NEUTRAL = (
    # cycle 195: trimmed 8 → 3 — removed 5 academic-only interjections
    # (此点尚需 / 此种情形 / 相关因素 / 若进一步 / 仔细推敲) that read
    # contemplative-academic when injected mid-text in informational /
    # workplace / general samples. Kept 3 entries that fit informational
    # registers (common-saying or "另一种角度" framing). Loses some pool
    # variety; bn=10 still has 3 distinct picks per pass.
    '事情可能并不如表面所示那般简单，需要更细致地审视。',
    '若从更多角度去考虑，结论恐怕会有不少不同之处。',
    '换个角度去看也成立，问题的另一面同样不容忽视。',
)


# Narrative-voice variants for novel style — character-internal / group
# beats only. Setting-specific lines (time-of-day, indoor / outdoor,
# weather) are deliberately excluded so the inserted paragraph doesn't
# contradict the surrounding scene state. Each is >=20 cn chars to pass
# the >=20 paragraph filter used by compute_paragraph_length_cv.
_PARA_INTERJECTION_NOVEL = (
    '众人都不约而同地陷入了一阵短暂的压抑沉默。',
    '他抬起头来，目光缓缓扫过众人脸上的神色一遍。',
    '他转过头去，目光在某处停留了片刻又缓缓移开。',
    '时间仿佛在这一刻悄然凝固住了，没有人开口说话。',
    '他心中暗暗思量了一阵子，事情似乎并不那么简单。',
    '气氛变得有些紧张了起来，众人之间默然不语好一会。',
    '他皱了皱眉头，似乎在心里反复斟酌着什么内容不解。',
    '他眯起了眼，神色之中流露出一种难以言喻的情绪。',
)


def insert_short_interjection_paragraph(text, target_cv=0.50, style=None,
                                        seed=None):
    """v5 P1.2 humanize counter-measure for paragraph_length_cv (d=-1.49).

    For multi-paragraph text whose paragraph-length CV is below target,
    insert a single short interjection paragraph (~20-22 cn chars) AFTER
    one of the longer existing paragraphs (top quartile by length).
    The interjection sharply lifts paragraph-length variance without
    restructuring existing paragraphs (cycle 28 lesson: split/merge of
    existing paragraphs has persistently negative ROI; this function
    only adds, never restructures).

    Two pools, picked by style:
      - novel  : narrative beats (atmosphere / action / dialogue gap)
      - other  : reflective neutral-formal sentences

    Skips:
      - Single-paragraph text
      - Text already varied (CV >= target)
      - When adjacent paragraph is a markdown header / list / bold
        subheader (would split a structural pair)
    """
    if seed is not None:
        random.seed(seed)

    paragraphs = text.split('\n\n')
    if len(paragraphs) < 4:
        return text

    lens = [len(re.findall(r'[一-鿿]', p)) for p in paragraphs]
    valid_pairs = [(i, l) for i, l in enumerate(lens) if l >= 20]
    if len(valid_pairs) < 3:
        return text
    valid_lens = [l for _, l in valid_pairs]
    m = sum(valid_lens) / len(valid_lens)
    if m == 0:
        return text
    var = sum((l - m) ** 2 for l in valid_lens) / len(valid_lens)
    cv = (var ** 0.5) / m

    if cv >= target_cv:
        return text

    sorted_pairs = sorted(valid_pairs, key=lambda x: -x[1])
    top_count = max(2, len(valid_pairs) // 4)
    top_indices = [i for i, _ in sorted_pairs[:top_count]]

    insert_after = random.choice(top_indices)
    next_idx = insert_after + 1
    if next_idx < len(paragraphs):
        next_lstrip = paragraphs[next_idx].lstrip()
        if (next_lstrip.startswith('#') or next_lstrip.startswith('- ') or
                next_lstrip.startswith('* ') or
                (next_lstrip.startswith('**') and
                 next_lstrip.rstrip().endswith('**'))):
            return text

    pool = _PARA_INTERJECTION_NOVEL if style == 'novel' \
        else _PARA_INTERJECTION_NEUTRAL
    interjection = random.choice(pool)

    new_paragraphs = list(paragraphs)
    new_paragraphs.insert(next_idx, interjection)
    return '\n\n'.join(new_paragraphs)


def boost_para_cv_via_merge(text, target_cv=0.40):
    """v5 P1 humanize counter-measure (merge variant).

    Walks paragraphs and, for any whose internal sentence-length CV is
    below target, merges a single pair of adjacent short-medium
    sentences with a comma. This removes one period (counter to the
    truncation variant in boost_para_sent_len_cv that adds one) so
    the punct_density LR contribution doesn't cancel the para-CV
    contribution, and the merged sentence typically clears the
    medium→long threshold (sent_len_long_frac coef in the longform LR
    is -0.44, so producing more longs helps).
    """
    paragraphs = text.split('\n\n')
    if len(paragraphs) < 2:
        return text
    return '\n\n'.join(_boost_one_para_via_merge(p, target_cv)
                       for p in paragraphs)


def boost_para_sent_len_cv(text, target_cv=0.40):
    """v5 P1 humanize counter-measure for stat_low_para_sent_len_cv (d=-2.08).

    For each paragraph (>=60 cn chars, >=3 sentences) where internal
    sentence-length CV is below target, truncate the longest sentence
    at its first comma so the paragraph contains at least one short
    sentence among its mediums. Single pass — does not iterate.

    Skips short paragraphs and applies the same guards as
    randomize_sentence_lengths Strategy B (attribution verbs, subordinate
    clause heads, bare causative continuators, paragraph-break tail).
    """
    paragraphs = text.split('\n\n')
    if len(paragraphs) < 2:
        # Single-paragraph text — signal doesn't apply.
        return text
    return '\n\n'.join(_boost_one_paragraph_cv(p, target_cv)
                       for p in paragraphs)


def randomize_sentence_lengths(text, aggressive=False, seed=None):
    """
    策略2: 刻意制造不均匀的句子长度分布。
    - 随机选 20% 的短句保持极短
    - 随机选 10% 的句子通过合并拉长
    - 制造"短-长-短-长-特长-短"的节奏
    """
    if seed is not None:
        random.seed(seed)

    # Split into sentences preserving punctuation
    parts = re.split(r'([。！？])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i]
        p = parts[i + 1] if i + 1 < len(parts) else ''
        if s.strip():
            sentences.append((s, p))
    # Handle trailing text
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append((parts[-1], ''))

    if len(sentences) < 4:
        return text

    merge_rate = 0.15 if not aggressive else 0.25
    truncate_rate = 0.15 if not aggressive else 0.25

    result = []
    i = 0
    while i < len(sentences):
        s, p = sentences[i]
        cn_len = len(re.findall(r'[\u4e00-\u9fff]', s))

        # Strategy A: merge short adjacent sentences into a long one
        if (i + 1 < len(sentences) and random.random() < merge_rate):
            s2, p2 = sentences[i + 1]
            cn_len2 = len(re.findall(r'[\u4e00-\u9fff]', s2))
            # Don't merge if adjacent sentence is a known reaction phrase (cycle 22
            # bug fix — short reactions inserted by `insert_short_reactions` were
            # being silently merged back, collapsing the short_frac signal).
            _reactions = (
                '的确', '确实如此', '颇有道理', '不无道理', '事出有因',
                '耐人寻味', '值得深思', '让人深思', '可见一斑', '有一定道理',
                '各有道理', '各有说法', '难以一概', '难以断言', '说来话长',
                '一言难尽',
            )
            s_stripped = s.strip()
            s2_stripped = s2.strip()
            # Paragraph boundary: split by [。！？] preserves \n\n as leading
            # whitespace on the next sentence. Merging would .lstrip() the
            # \n\n away and collapse two paragraphs into one — discourse
            # structure loss (Petalses issue #5).
            if '\n' in s2 or s_stripped in _reactions or s2_stripped in _reactions:
                pass
            elif cn_len + cn_len2 < 100:
                merged = s.rstrip() + '，' + s2.lstrip()
                result.append(merged + p2)
                i += 2
                continue

        # Strategy B: truncate longer sentences to their first clause (creates short punchy sentences)
        if cn_len > 20 and cn_len < 50 and random.random() < truncate_rate:
            # Truncate to first clause (split at first comma), keep rest as next sentence
            comma_pos = s.find('，')
            if comma_pos > 5 and comma_pos < len(s) - 5:
                first_part = s[:comma_pos]
                first_stripped = first_part.lstrip()
                # Guard 0: don't truncate when the first_part fragment after the
                # last paragraph break is too short. The [。！？] split doesn't
                # respect \n\n, so a segment can span "## header\n\n现在，X..."
                # — truncating yields "## header\n\n现在。X..." stranding a
                # 2-char fragment after the section header.
                last_nl = first_part.rfind('\n')
                if last_nl >= 0:
                    tail_cn = len(re.findall(r'[一-鿿]',
                                             first_part[last_nl + 1:]))
                    if tail_cn < 3:
                        result.append(s + p)
                        i += 1
                        continue
                # Guard 1: skip if first part ends in an attribution/reporting verb.
                # Otherwise "X 指出，" becomes "X 指出。" + bare clause — broken grammar.
                _attribution_suffixes = (
                    '指出', '表明', '认为', '揭示', '发现', '显示', '提出',
                    '说', '称', '讲', '强调', '主张', '断言',
                )
                if first_part.endswith(_attribution_suffixes):
                    result.append(s + p)
                    i += 1
                    continue
                # Guard 2: skip if first part is a subordinate clause (starts with
                # 随着/鉴于/为了/由于/尽管/虽然/如果 etc.). Splitting at comma would
                # leave a fragment that can't stand alone: "随着X的发展。Y" is broken.
                _subordinate_prefixes = (
                    '随着', '鉴于', '为了', '由于', '尽管', '虽然',
                    '如果', '假如', '若是', '倘若', '要是', '即便', '纵然',
                    '除了', '除非', '只要', '只有', '无论', '不管',
                    '当', '每当', '一旦',
                    # cycle 201: 面对X / 处在X = context introducer that needs
                    # a main clause. Splitting at comma leaves a fragment.
                    # ('在' kept out — too broad; handled by suffix guard below)
                    '面对', '处在',
                )
                if first_stripped.startswith(_subordinate_prefixes):
                    result.append(s + p)
                    i += 1
                    continue
                # cycle 201: context-introducer SUFFIXES that need a main
                # clause (covers "在X的背景下" cycle-190 alts: "...这种局面，"
                # "...这个情境里，" "...之中，"). Catches the "在" case
                # without blocking all "在..." sentences.
                _context_suffixes = (
                    '这种局面', '这种情况', '这个情境里', '这种背景下',
                    '之中', '的背景下',
                )
                if first_part.endswith(_context_suffixes):
                    result.append(s + p)
                    i += 1
                    continue
                # Guard 3: skip if next clause starts with a bare causative
                # verb (使/使得/导致/造成 etc.) OR a continuation marker
                # (同时/此外/另外/更/不仅/而且/进而/继而/充分/进一步/同样).
                # These all assume the prior clause's subject/context — splitting
                # creates fragment "X。同时Y。" which reads as orphaned.
                # cycle 206 (sway 标点符号奇怪): added 同时/充分/进一步 etc.
                # Audit on workplace example showed pattern "工作效率，同时也Y，
                # 充分体现Z" splitting into 3 short sentences with multiple
                # paragraph-end periods — sway flagged as awkward.
                _bare_continuators = (
                    '使得', '使', '导致', '引起', '造成', '致使',
                    '同时', '同样', '此外', '另外', '更', '不仅', '而且',
                    '进而', '继而', '充分', '进一步', '同时也',
                )
                rest_after_comma = s[comma_pos + 1:].lstrip()
                if rest_after_comma.startswith(_bare_continuators):
                    result.append(s + p)
                    i += 1
                    continue
                rest_part = s[comma_pos + 1:]
                result.append(first_part + p)
                # Push the rest as a new "sentence" to be processed
                if rest_part.strip():
                    result.append(rest_part + '。')
                i += 1
                continue

        result.append(s + p)
        i += 1

    return ''.join(result)


# ═══════════════════════════════════════════════════════════════════
#  Strategy 3: Noise expression injection
# ═══════════════════════════════════════════════════════════════════

def _dialogue_density_local(text):
    """Fraction of chars inside Chinese dialogue quotes. AI novels use a
    mix of curly U+201C/D (“”), corner U+300C/D (「」), and ASCII pairs
    (which some models output instead). Threshold 0.08 flags narrative."""
    n = 0
    for pat in (r'“[^“”]{3,}?”', r'「[^「」]{3,}?」'):
        for m in re.findall(pat, text):
            n += len(m)
    # ASCII " pairs: split on ", odd-indexed segments are inside quotes
    parts = text.split('"')
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            if len(parts[i]) >= 3:
                n += len(parts[i])
    return n / max(1, len(text))


# Narrative-safe subset of NOISE_EXPRESSIONS categories. filler/personal/
# transition_casual inject 1st-person author voice or oral fillers that
# break 3rd-person fiction register.
_NARRATIVE_SAFE_CATEGORIES = ['hedging', 'uncertainty', 'self_correction']


def inject_noise_expressions(text, density=0.15, style='general'):
    """
    策略3: 在句子间或句中适当位置插入噪声表达。
    density: 大约每多少句插入一个（0.15 ≈ 每 6-7 句一个）
    style: general / academic
    """
    # cycle 152: when style='general' but the text has 2+ markdown
    # headers (academic survey / technical article), the 'filler' /
    # 'transition_casual' / 'personal' categories from NOISE_EXPRESSIONS
    # ('当然了' / '坦白讲' / '不瞒你说' etc.) read off-register inside
    # formal prose. Promote to the academic noise subset, which keeps
    # only hedging / self_correction / uncertainty.
    if style == 'general':
        n_md_headers = sum(1 for line in text.split('\n')
                           if re.match(r'^\s*#{1,6}\s', line))
        if n_md_headers >= 2:
            style = 'academic'

    if style == 'academic':
        categories = NOISE_ACADEMIC_CATEGORIES
        expressions = NOISE_ACADEMIC_EXPRESSIONS
    else:
        categories = list(NOISE_EXPRESSIONS.keys())
        expressions = NOISE_EXPRESSIONS
        # Narrative guard: if text is dialogue-heavy, drop categories that
        # break 3rd-person voice (filler/personal/transition_casual).
        if _dialogue_density_local(text) >= 0.08:
            categories = [c for c in categories if c in _NARRATIVE_SAFE_CATEGORIES]
            if not categories:
                return text

    # Split into sentences
    parts = re.split(r'([。！？])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i]
        p = parts[i + 1] if i + 1 < len(parts) else ''
        if s.strip():
            sentences.append([s, p])
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append([parts[-1], ''])

    if len(sentences) < 3:
        return text

    # Track expressions already injected in this run. Re-injecting the same
    # phrase ("\u5f80\u6df1\u4e86\u8bb2" / "\u5e73\u5fc3\u800c\u8bba") three times in one sample reads as a
    # tic, which detect_cn flags as repetitive and a human reviewer flags as
    # robot-style.
    used = set()

    # cycle 203 (sway directive \u8bed\u53e5\u901a\u987a\u4f18\u5148): track which paragraphs already
    # had a noise injection. Multiple injections per paragraph create
    # "\u5728\u6211\u770b\u6765\uff0cX\u3002\u6ce8\u610f\uff0cY\u3002\u8bf4\u5230\u5e95\uff0cZ" robotic chains. Hard cap = 1
    # injection per paragraph. Identifies paragraph by the cumulative \n\n
    # count in text up to the sentence position.
    para_injected = {}

    injected = 0
    cum_text = ''
    for i in range(len(sentences)):
        s_text = sentences[i][0]
        s_punct = sentences[i][1] or ''
        # cycle 203: track cumulative text to identify current paragraph
        # (paragraph = chunk between \n\n breaks). Update at top so all
        # `continue` branches keep para_idx in sync.
        para_idx = cum_text.count('\n\n')
        cum_text += s_text + s_punct
        # Skip the last sentence (avoid orphaned expressions)
        if i >= len(sentences) - 1:
            continue
        # Skip very short sentences
        if len(re.findall(r'[\u4e00-\u9fff]', s_text)) < 8:
            continue
        # Skip sentences that contain dialogue quotes. Injecting a noise
        # expression into a quoted line puts narrator filler inside a
        # character's mouth \u2014 awkward and breaks dialogue flow.
        if '"' in s_text or '\u201c' in s_text or '\u201d' in s_text or '\u300c' in s_text or '\u300d' in s_text:
            continue
        # Cycle 57/58: skip sentences that start with markdown structural
        # markers (# heading / - * bullet / **bold** subheader / 1. 2.
        # numbered list). Injecting '\u4e0d\u7792\u4f60\u8bf4\uff0c' before '#### 2.2 ...' or
        # '\u5728\u6211\u770b\u6765\uff0c**3. \u54c1\u724c\u5efa\u8bbe\uff1a\u6587\u5316\u2026**' corrupts the structural marker.
        # Cycle 58 widens the **-prefix check from "starts AND ends with **"
        # (pure bold subheader) to just "starts with **" \u2014 covers hybrid
        # forms like '**1. \u8d44\u6e90\u74f6\u9888\uff1a** \u9ad8\u5e76\u53d1\u610f\u5473\u7740\u2026' that the cycle 57
        # check missed (audit found 34 longform samples with this pattern).
        s_lstripped = s_text.lstrip()
        # cycle 203 (sway directive 语句通顺优先): skip if sentence already
        # starts with a SHORT transition marker. These come from
        # patterns_cn.json replacements (值得注意的是→注意, 综上所述→总之,
        # 其次→另外/此外, etc.). Stacking noise on top reads as
        # "在我看来，注意，X..." — multiple transitions piled up, robotic.
        # Trade: drops some LR-favorable noise, accepted per sway directive.
        _existing_transitions = (
            '注意，', '特别说一下，', '要提醒的是，', '总之，', '说到底，',
            '简单讲，', '归结起来，', '另外，', '此外，', '还有，',
            '可以看到，', '很明显，', '你会发现，',
            '一开始，', '最初，', '起头，', '先说，',
            '接着，', '然后，', '再就是，', '最后说一点，',
        )
        if s_lstripped.startswith(_existing_transitions):
            continue
        # cycle 203: per-paragraph injection cap = 1 (sway 语句通顺优先).
        # Skip if this paragraph already had an injection — prevents
        # "在我看来，X。注意，Y" cross-sentence stacking.
        if para_injected.get(para_idx, 0) >= 1:
            continue
        # cycle 203 sub: also skip if the same paragraph (the one we're
        # in, or that the current sentence will land in) already contains
        # any of the existing-transition markers (from replacements). This
        # catches "注意，X。" + "在我看来，Y" same-paragraph stacking
        # where 注意 came from values_注意的是 replacement, not noise.
        # Build the paragraph slice: all sentences sharing this paragraph.
        para_slice = ''
        running_para = 0
        for j in range(len(sentences)):
            if running_para == para_idx:
                para_slice += sentences[j][0] + (sentences[j][1] or '')
            running_para += (sentences[j][0] + (sentences[j][1] or '')).count('\n\n')
            if running_para > para_idx:
                break
        if any(t in para_slice for t in _existing_transitions):
            continue
        if s_lstripped.startswith('#') or s_lstripped.startswith('- ') or s_lstripped.startswith('* '):
            continue
        if s_lstripped.startswith('**'):
            continue
        if re.match(r'^\d+[.\u3002\uff0e)\uff09]', s_lstripped):
            continue
        if random.random() > density:
            continue

        cat = random.choice(categories)
        expr_list = expressions.get(cat, [])
        if not expr_list:
            continue
        avail = [e for e in expr_list if e not in used]
        if not avail:
            avail = expr_list  # fallback when category exhausted
        expr = random.choice(avail)
        used.add(expr)

        s, p = sentences[i]

        # Preserve leading whitespace (\n\n paragraph breaks) — sentences
        # that start a new paragraph have \n\n at their head (artifact of
        # the [。！？] split). .lstrip() would eat those and collapse
        # paragraph structure.
        leading_ws_len = len(s) - len(s.lstrip())
        leading = s[:leading_ws_len]
        s_body = s[leading_ws_len:]

        # Decide insertion position
        if cat in ('hedging', 'filler', 'personal', 'transition_casual'):
            # Insert at sentence beginning (after any paragraph break)
            s = leading + expr + '，' + s_body
        elif cat in ('self_correction', 'uncertainty'):
            # Insert mid-sentence at a comma
            comma_pos = s_body.find('，')
            if comma_pos > 3:
                s = leading + s_body[:comma_pos + 1] + expr + '，' + s_body[comma_pos + 1:]
            else:
                s = leading + expr + '，' + s_body

        sentences[i] = [s, p]
        injected += 1
        # cycle 203: bump per-paragraph counter for cap enforcement
        para_injected[para_idx] = para_injected.get(para_idx, 0) + 1

    return ''.join(s + p for s, p in sentences)


# ─── Core Transforms ───

def remove_three_part_structure(text):
    """Remove 首先/其次/最后, 第一/第二/第三 patterns"""
    # Don't just delete — replace with natural transitions
    replacements = [
        (r'首先[，,]\s*', ''),
        (r'其次[，,]\s*', lambda m: random.choice(['另外，', '此外，', ''])),
        (r'最后[，,]\s*', lambda m: random.choice(['还有，', ''])),  # cycle 208: drop 最后说一点 (awkward in essays)
        (r'第一[，,、]\s*', ''),
        (r'第二[，,、]\s*', lambda m: random.choice(['接着，', '然后，', ''])),
        (r'第三[，,、]\s*', lambda m: random.choice(['还有，', '再就是，', ''])),
        (r'第[四五六七八九][，,、]\s*', lambda m: random.choice(['另外，', ''])),
        (r'其一[，,、]\s*', ''),
        (r'其二[，,、]\s*', lambda m: random.choice(['另外，', ''])),
        (r'其三[，,、]\s*', lambda m: random.choice(['还有，', ''])),
    ]
    
    for pattern, repl in replacements:
        if callable(repl):
            text = re.sub(pattern, repl, text)
        else:
            text = re.sub(pattern, repl, text)
    
    return text

def replace_phrases(text, casualness=0.3):
    """Replace AI phrases with natural alternatives (context-aware)"""
    # Apply regex replacements FIRST (per-sentence, max 1 regex replacement per sentence)
    # Split by sentence-ending punctuation to handle multiple templates in same line
    parts = re.split(r'([。！？\n])', text)
    rebuilt = []
    for part in parts:
        replaced = False
        for pattern, alternatives in REGEX_REPLACEMENTS.items():
            if replaced:
                break
            if isinstance(alternatives, str):
                alternatives = [alternatives]
            try:
                match = re.search(pattern, part)
                if match:
                    replacement = random.choice(alternatives)
                    expanded = match.expand(replacement)
                    part = part[:match.start()] + expanded + part[match.end():]
                    replaced = True
            except re.error:
                pass
        rebuilt.append(part)
    text = ''.join(rebuilt)
    
    # Then plain replacements, sorted by length (longest first) to avoid partial matches
    sorted_phrases = sorted(PLAIN_REPLACEMENTS.keys(), key=len, reverse=True)
    
    for phrase in sorted_phrases:
        alternatives = PLAIN_REPLACEMENTS[phrase]
        if isinstance(alternatives, str):
            alternatives = [alternatives]
        
        if phrase in text:
            # Filter out alternatives that contain the phrase as a substring —
            # those cause infinite re-match loops (e.g. 相反 -> 相反地 reinserts
            # 相反). Without this, slow-path bug: cycle 2 HC3 500 hang, cycle 13
            # longform benchmark kill on samples 85/86/133/144 (all had 相反).
            safe_alts = [alt for alt in alternatives if phrase not in alt]
            if not safe_alts:
                continue
            # Dedupe replacement choices for this phrase. pick_best_replacement
            # is deterministic on perplexity, so when the same phrase occurs
            # multiple times in a long sample it gets rewritten to the same
            # alternative every iteration ('可能引起' x4-5 in audit). Track
            # which alts have been used and prefer unused ones; fall back to
            # the full safe list once exhausted.
            used = set()
            replacement = pick_best_replacement(text, phrase, safe_alts)
            text = text.replace(phrase, replacement, 1)
            used.add(replacement)
            while phrase in text:
                avail = [a for a in safe_alts if a not in used]
                if not avail:
                    # Cycle exhausted — clear `used` so the next round
                    # rotates through the alts again instead of falling
                    # back to a single deterministic pick. Without this
                    # reset, sample 38 of the longform corpus rewrites
                    # 9 occurrences of '然后' as 6×'随后' + '接着' + '之后'
                    # + '随后' instead of an even distribution.
                    used.clear()
                    avail = safe_alts
                replacement = pick_best_replacement(text, phrase, avail)
                text = text.replace(phrase, replacement, 1)
                used.add(replacement)

    return text

def merge_short_sentences(text, min_len=8):
    """Merge overly short consecutive sentences, with burstiness guard."""
    # Measure burstiness before restructuring
    burst_before = _compute_burstiness(text)

    sentences = re.split(r'([。！？])', text)
    if len(sentences) < 4:
        return text
    
    result = []
    i = 0
    while i < len(sentences) - 1:
        sent = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        # Check if this and next sentence are both short
        next_sent = sentences[i + 2] if i + 2 < len(sentences) else ''
        
        if len(sent.strip()) < min_len and len(next_sent.strip()) < min_len and next_sent.strip():
            # Don't merge across paragraph boundaries — \n\n leading
            # next_sent would be stripped by .strip(), collapsing paragraphs.
            if '\n' in sent or '\n' in next_sent:
                result.append(sent + punct)
                i += 2
            else:
                # Merge with comma
                merged = sent.strip() + '，' + next_sent.strip()
                next_punct = sentences[i + 3] if i + 3 < len(sentences) else '。'
                result.append(merged + next_punct)
                i += 4
        else:
            result.append(sent + punct)
            i += 2
    
    # Handle remaining
    while i < len(sentences):
        result.append(sentences[i])
        i += 1
    
    new_text = ''.join(result)

    # Burstiness guard: if merging made text more uniform, revert
    if burst_before is not None:
        burst_after = _compute_burstiness(new_text)
        if burst_after is not None and burst_after < burst_before * 0.8:
            return text  # revert — merging reduced burstiness too much

    return new_text

def split_long_sentences(text, max_len=80):
    """Split overly long sentences at natural breakpoints, with burstiness guard."""
    burst_before = _compute_burstiness(text)

    sentences = re.split(r'([。！？])', text)
    result = []
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        chinese_len = len(re.findall(r'[\u4e00-\u9fff]', sent))
        
        if chinese_len > max_len:
            # Find natural split points: 但是/不过/然而/同时/而且
            split_points = [
                (m.start(), m.group()) for m in
                re.finditer(r'[，,](但是|不过|然而|同时|而且|所以|因此|另外)', sent)
            ]

            def _tail_too_short(part):
                # Skip splits that would strand a tiny fragment after the most
                # recent paragraph/line break. Sentences split by [。！？] can
                # span "## header\n\nX，Y" so a comma-split produces broken
                # "## header\n\nX。Y" output.
                last_nl = part.rfind('\n')
                if last_nl < 0:
                    return False
                tail_cn = len(re.findall(r'[一-鿿]', part[last_nl + 1:]))
                return tail_cn < 3

            if split_points:
                # Split at the most central point
                mid = len(sent) // 2
                best = min(split_points, key=lambda x: abs(x[0] - mid))
                part1 = sent[:best[0]]
                part2 = sent[best[0]+1:]  # Skip the comma
                if _tail_too_short(part1):
                    result.append(sent + punct)
                else:
                    result.append(part1 + '。' + part2 + punct)
            else:
                # Split at a comma near the middle. Filter commas whose
                # following clause starts with a bare causative verb
                # (使得/导致/etc.) — splitting there yields "X。使得Y" which
                # strands a subject-less verb.
                _bare_continuators = (
                    '使得', '使', '导致', '引起', '造成', '致使',
                )
                def _safe_comma(idx):
                    rest = sent[idx + 1:].lstrip()
                    return not rest.startswith(_bare_continuators)
                commas = [m.start() for m in re.finditer(r'[，,]', sent)
                          if _safe_comma(m.start())]
                if commas:
                    mid = len(sent) // 2
                    best_comma = min(commas, key=lambda x: abs(x - mid))
                    part1 = sent[:best_comma]
                    part2 = sent[best_comma+1:]
                    if _tail_too_short(part1):
                        result.append(sent + punct)
                    else:
                        result.append(part1 + '。' + part2 + punct)
                else:
                    result.append(sent + punct)
        else:
            result.append(sent + punct)
    
    # Handle remaining
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    new_text = ''.join(result)

    # Burstiness guard: if splitting made text more uniform, revert
    if burst_before is not None:
        burst_after = _compute_burstiness(new_text)
        if burst_after is not None and burst_after < burst_before * 0.8:
            return text

    return new_text

def vary_paragraph_rhythm(text):
    """Break uniform paragraph lengths by merging or splitting"""
    paragraphs = text.split('\n\n')
    if len(paragraphs) < 3:
        return text

    # v5 P1.2 guard (cycle 143): if paragraph-length CV is already
    # adequate (>=0.40, near human distribution), skip merge/split.
    # cycle 142 found that further structural tweaks on already-varied
    # paragraphs push the distribution back toward uniform — a stuck
    # academic sample went from CV 0.405 to 0.320 after the full
    # pipeline because a long paragraph got split, averaging the
    # distribution down. Same threshold as compute_paragraph_length_cv
    # consumes (>=20 cn chars per paragraph).
    cn_lens = [len(re.findall(r'[一-鿿]', p)) for p in paragraphs]
    valid_lens = [l for l in cn_lens if l >= 20]
    if len(valid_lens) >= 3:
        m_cn = sum(valid_lens) / len(valid_lens)
        if m_cn > 0:
            var = sum((l - m_cn) ** 2 for l in valid_lens) / len(valid_lens)
            cv = (var ** 0.5) / m_cn
            if cv >= 0.40:
                return text

    lengths = [len(p) for p in paragraphs]
    avg_len = sum(lengths) / len(lengths) if lengths else 100

    def _is_md_header(p):
        # Markdown headers ('# ', '## ', '### ' …), bullets, bold section
        # subheaders, numbered list items, and dialogue lines are
        # deliberately short structural paragraphs; merging them collapses
        # document structure (sample 63 of longform corpus: ## headers
        # lost; cycle-44 audit: bold subheaders + numbered list items;
        # cycle-46 audit: novel sample 1323 had two dialogue paragraphs
        # like '"嗯，我很喜欢。"' merged into one block, losing the
        # turn-by-turn formatting).
        s = p.lstrip()
        if s.startswith('#') or s.startswith('- ') or s.startswith('* '):
            return True
        if s.startswith('**') and s.rstrip().endswith('**'):
            return True
        if re.match(r'^\d+[.。．)）]', s):
            return True
        # Dialogue line (Chinese / Western quotes / Japanese 「」)
        if s and s[0] in '"“「':
            return True
        return False

    result = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]

        # Randomly merge short adjacent paragraphs (skip markdown headers /
        # bullet items — those are deliberately short structural markers).
        if (i + 1 < len(paragraphs) and
            len(para) < avg_len * 0.6 and
            len(paragraphs[i + 1]) < avg_len * 0.6 and
            not _is_md_header(para) and
            not _is_md_header(paragraphs[i + 1]) and
            random.random() < 0.4):
            merged = para + '\n' + paragraphs[i + 1]
            result.append(merged)
            i += 2
            continue
        
        # Split long paragraphs
        if len(para) > avg_len * 1.5:
            sentences = re.split(r'([。！？])', para)
            mid = len(sentences) // 2
            # Ensure we split at a sentence boundary (every other element is punctuation)
            if mid % 2 == 1:
                mid -= 1
            part1 = ''.join(sentences[:mid])
            part2 = ''.join(sentences[mid:])
            if part1.strip() and part2.strip():
                result.append(part1.strip())
                result.append(part2.strip())
                i += 1
                continue
        
        result.append(para)
        i += 1
    
    return '\n\n'.join(result)

def reduce_punctuation(text):
    """Reduce excessive punctuation intelligently"""
    # Replace some semicolons with commas or periods
    parts = text.split('；')
    if len(parts) > 3:
        result_parts = [parts[0]]
        for i, part in enumerate(parts[1:], 1):
            # Alternate between comma and period
            if i % 2 == 0:
                result_parts.append('。' + part.lstrip())
            else:
                result_parts.append('，' + part)
        text = ''.join(result_parts)
    
    # Limit consecutive em dashes
    text = re.sub(r'——', '—', text)
    
    return text

def cap_transition_density(text, target=6.0):
    """Drop clause-initial transition phrases until density <= target.

    Runs AFTER all other humanize passes. Keeps transitions that are
    low-density already; removes excess probabilistically. Detect threshold
    fires at density > 8 per 1000 chars, so target 6 gives margin.
    """
    try:
        from ngram_model import _TRANSITION_PHRASES
    except ImportError:
        from scripts.ngram_model import _TRANSITION_PHRASES

    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cn_chars < 100:
        return text

    hits = sum(text.count(p) for p in _TRANSITION_PHRASES)
    density = hits / cn_chars * 1000
    if density <= target:
        return text

    remove_prob = min(0.9, (density - target) / density)

    for phrase in sorted(_TRANSITION_PHRASES, key=len, reverse=True):
        esc = re.escape(phrase)
        pattern = re.compile(r'(^|[。！？\n])(' + esc + r')([，,、])?')

        def sub(m):
            if random.random() < remove_prob:
                return m.group(1)
            return m.group(0)

        text = pattern.sub(sub, text)

    return text


def inject_sentence_particles(text, rate=0.15):
    """Append casual sentence-ending particles (吧/嘛/呗) to random statements.

    Intended for casual/social/chat scenes only. Skips questions/exclamations
    (already tonal) and sentences already ending in a particle. Short sentences
    skipped (too brittle), very long ones skipped (feels forced).
    """
    parts = re.split(r'([。！？])', text)
    particles = ['吧', '嘛', '呗']
    for i in range(0, len(parts) - 1, 2):
        sent = parts[i]
        punct = parts[i + 1] if i + 1 < len(parts) else ''
        if punct in '！？':
            continue
        cn = sum(1 for c in sent if '\u4e00' <= c <= '\u9fff')
        if cn < 6 or cn > 40:
            continue
        rstripped = sent.rstrip()
        if rstripped and rstripped[-1] in '吧嘛呗呢啊哦嗯哈的了':
            continue
        if random.random() < rate:
            parts[i] = rstripped + random.choice(particles)
    return ''.join(parts)


def add_casual_expressions(text, casualness=0.3):
    """Inject casual/human expressions"""
    if casualness < 0.2:
        return text
    
    casual_openers = ['说实话', '其实', '确实', '讲真', '坦白说']
    casual_transitions = ['话说回来', '说到这个', '不过呢', '但是吧']
    casual_endings = ['就是这么回事', '差不多就这样', '大概就这些']
    
    sentences = re.split(r'([。！？])', text)
    result = []
    added = 0
    total = len(sentences) // 2
    max_additions = max(1, int(total * casualness * 0.3))
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if added < max_additions and random.random() < casualness * 0.2:
            if i == 0:
                opener = random.choice(casual_openers)
                sent = opener + '，' + sent
            elif i > total:
                transition = random.choice(casual_transitions)
                sent = transition + '，' + sent
            added += 1
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    return ''.join(result)

def shorten_paragraphs(text, max_length=150):
    """Break long paragraphs for social/chat scenes"""
    paragraphs = text.split('\n\n')
    result = []
    
    for para in paragraphs:
        if len(para) > max_length:
            sentences = re.split(r'([。！？])', para)
            chunks = []
            current = ''
            
            for i in range(0, len(sentences) - 1, 2):
                sent = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
                if len(current) + len(sent) > max_length and current:
                    chunks.append(current.strip())
                    current = sent
                else:
                    current += sent
            
            if current.strip():
                chunks.append(current.strip())
            
            result.extend(chunks)
        else:
            result.append(para)
    
    return '\n\n'.join(result)

def diversify_vocabulary(text):
    """Reduce word repetition by using synonyms"""
    # Common overused words and their alternatives
    diversity_map = {
        '进行': ['做', '开展', '实施', '推进'],
        '实现': ['达到', '做到', '完成'],
        '提供': ['给出', '带来'],  # Cycle 63: dropped 拿出 (see WORD_SYNONYMS comment)
        '具有': ['有', '拥有', '带有'],
        '进一步': ['深入'],  # cycle 203: drop 更/再 (broken in 更进一步)
        '不断': ['持续', '一直', '始终'],
        # '有效' skipped: attributive/adj usage (有效证件) breaks with verb substitutes
        '积极': ['主动', '热心'],
        '促进': ['推动', '带动'],
        '加强': ['强化', '增强'],
        '提高': ['提升', '增加'],
        # cycle 164: dropped '重要' — same compound-breakage as
        # WORD_SYNONYMS upstream (重要性 → 核心性, 至关重要 → 至关核心
        # both broken).
    }
    
    for word, alts in diversity_map.items():
        count = text.count(word)
        if count > 2:
            # Keep first occurrence, replace subsequent
            first = True
            parts = text.split(word)
            result = [parts[0]]
            for part in parts[1:]:
                if first:
                    result.append(word)
                    first = False
                else:
                    result.append(random.choice(alts))
                result.append(part)
            text = ''.join(result)
    
    return text

# ─── Main Humanize Pipeline ───

def _estimate_source_aiscore(text):
    """Quick pre-detect of how AI-like the input is. Returns 0-100 score or None."""
    try:
        from detect_cn import detect_patterns, calculate_score
    except ImportError:
        try:
            from scripts.detect_cn import detect_patterns, calculate_score
        except ImportError:
            return None
    try:
        issues, metrics = detect_patterns(text)
        return calculate_score(issues, metrics)
    except Exception:
        return None


DEFAULT_BEST_OF_N = 10


def humanize(text, scene='general', aggressive=False, seed=None, best_of_n=DEFAULT_BEST_OF_N, style=None):
    """Apply all humanization transformations in order.

    Graduated intensity based on source AI-score (pre-detect):
      - score < 15 (conservative): only phrase replacement + punctuation cleanup
      - score 15-39 (moderate): + restructure + lighter bigram substitution
      - score >= 40 (full): entire pipeline including noise injection
    Aggressive flag forces 'full' tier.

    best_of_n: if set to an integer, runs humanize N times with different seeds
    and returns the output that scores lowest on the LR ensemble (requires
    scripts/lr_coef_cn.json). Useful when minimizing LR score matters more
    than latency.

    Rationale: HC3 benchmark showed that full pipeline on already-clean text
    (source score < 15) adds spurious AI patterns (段落均匀/熵低) via noise
    injection, sometimes INCREASING detected score. Tiered intensity avoids this.
    """
    if best_of_n and best_of_n > 1:
        try:
            from ngram_model import compute_lr_score
        except ImportError:
            from scripts.ngram_model import compute_lr_score
        base_seed = seed if seed is not None else 42
        candidates = []
        for i in range(best_of_n):
            s = base_seed + i
            out = humanize(text, scene=scene, aggressive=aggressive,
                           seed=s, best_of_n=None, style=style)
            lr = compute_lr_score(out)
            score = lr['score'] if lr else 50
            candidates.append((score, s, out))
        candidates.sort(key=lambda x: x[0])
        return candidates[0][2]

    if seed is not None:
        random.seed(seed)

    config = SCENES.get(scene, SCENES['general'])
    casualness = config.get('casualness', 0.3)
    if aggressive:
        casualness = min(1.0, casualness + 0.3)

    source_score = _estimate_source_aiscore(text)
    # Tier thresholds calibrated on HC3-Chinese: most naturally-written ChatGPT
    # scores 5-25 on detect_cn. Full pipeline on very-clean input (< 5) adds
    # spurious noise. Moderate tier skips noise/sentence-randomization but keeps
    # everything else. Trade picks up most of the full-tier gains with fewer regressions.
    if aggressive or source_score is None or source_score >= 25:
        tier = 'full'
    elif source_score >= 5:
        tier = 'moderate'
    else:
        tier = 'conservative'

    # Pass 1: Structure cleanup — always run (safe, targeted)
    text = remove_three_part_structure(text)
    text = replace_phrases(text, casualness)

    # Pass 2: Deep sentence restructuring — all tiers (with moderate strength in conservative)
    try:
        from restructure_cn import deep_restructure
    except ImportError:
        try:
            from scripts.restructure_cn import deep_restructure
        except ImportError:
            deep_restructure = None
    if deep_restructure:
        # Conservative keeps restructure but with aggressive=False to be gentler
        text = deep_restructure(text, aggressive=aggressive, scene=scene)

    # Pass 2b: Sentence merge/split
    if config.get('merge_short', False):
        text = merge_short_sentences(text)
    if config.get('split_long', False):
        text = split_long_sentences(text)

    # Pass 3: Rhythm and variety — diversify all tiers, rhythm only moderate+
    text = reduce_punctuation(text)
    text = diversify_vocabulary(text)
    if tier != 'conservative' and config.get('rhythm_variation', False):
        text = vary_paragraph_rhythm(text)

    # Pass 4: Scene-specific — only at full tier
    if tier == 'full':
        if config.get('add_casual', False) or aggressive:
            text = add_casual_expressions(text, casualness)
            # Sentence-end particles (吧/嘛/呗) — cycle 14 tried but caused xhs regression
            # (seed=42: 53 → 59). Random state shift + downstream interaction. Parked.
        if config.get('shorten_paragraphs', False):
            text = shorten_paragraphs(text)

    # ── Perplexity-boosting strategies — tier-gated ──
    # Bigram substitution active in moderate+full (safe, targeted)
    if tier != 'conservative':
        bigram_strength = 0.5 if aggressive else 0.3
        if tier == 'moderate':
            bigram_strength *= 0.6
        # Route bigram substitution through the novel-register filter when
        # --style novel is active. NOVEL_BLACKLIST_CANDIDATES strips the
        # overtly colloquial / book-Chinese substitutes ('搞'/'拉高'/'业已'/
        # '早就') that break narrative register, while keeping
        # ('察觉'/'识破') that academic mode rejects.
        bigram_scene = 'novel' if style == 'novel' else scene
        text = reduce_high_freq_bigrams(text, strength=bigram_strength, scene=bigram_scene)

    # Noise + sentence randomization only at full tier — these are the operations
    # that on HC3 sometimes added spurious AI patterns to already-clean text.
    if tier == 'full' and _USE_NOISE:
        noise_density = 0.25 if aggressive else 0.15
        # Novel/fiction register: noise injection (regardless of expression
        # subset) frequently lands on prepositional or vocative sentence heads
        # ('作为...' / '人物名+verb') and reads as awkward. Lean on word
        # substitutions + transition cap + paraphrase replacement for delta
        # in novel mode instead.
        if style != 'novel':
            # Cycle 104: route academic scene through NOISE_ACADEMIC_EXPRESSIONS
            # subset (hedging / self_correction / uncertainty). Cycle 54 tried
            # this and lost -2 academic hero, but cycles 76-101 since cleaned
            # the pool of self-defeating entries — second attempt with the
            # tighter pool. Audit found 20+ filler / transition_casual /
            # personal injections in academic samples ('不瞒你说' / '说到底' /
            # '讲真' / '约莫' / '估摸着') that read off-register.
            noise_style = 'academic' if scene == 'academic' else 'general'
            text = inject_noise_expressions(text, density=noise_density, style=noise_style)
        text = randomize_sentence_lengths(text, aggressive=aggressive, seed=seed)

    # v5 P1 humanize counter-measure for stat_low_para_sent_len_cv. The
    # truncation variant (boost_para_sent_len_cv) was shelved because
    # adding a period bumps punct_density and cancels the para-CV win.
    # The merge variant lifts a uniform paragraph by combining two
    # adjacent short-medium sentences with a comma — removing one
    # period, often pushing the merged sentence over the long threshold,
    # both of which point LR away from AI. n=20 sweep at target=0.40
    # showed avg LR delta -0.95 with zero regressions.
    text = boost_para_cv_via_merge(text)

    # v5 P1.2 humanize counter-measure for paragraph_length_cv (LR coef
    # -1.99 on longform). For multi-paragraph text whose paragraph
    # length CV is below 0.60, insert a single 22-24 cn-char reflection
    # paragraph after one of the longer existing paragraphs. Skipped
    # for novel style (narrative paragraphs differ; reflective
    # interjections read off-register). n=30 by-genre sweep:
    #   novel    skipped 10/10 ✓
    #   academic fired 4/10, LR delta 0.00 (neutral)
    #   news     fired 10/10, LR avg -2.10 (3 down / 1 up / 6 same)
    text = insert_short_interjection_paragraph(text, target_cv=0.60,
                                               style=style, seed=seed)

    # v5 P1.3 humanize counter-measure for cross_para_3gram_repeat (LR
    # coef +2.24 on longform). Replaces a few CiLin-known 2-char words
    # that recur across paragraphs with scene-filtered synonyms,
    # breaking the cross-paragraph trigram repetition. n=20 sweep at
    # max_replacements=4: fired 20/20, LR delta avg -1.65, zero
    # regressions.
    text = reduce_cross_para_3gram_repeat(text, max_replacements=4,
                                          scene=scene, style=style,
                                          seed=seed)

    # Final transition cap — AI overuses 首先/然而/此外/因此 etc, detect fires
    # density > 8/1000 chars. Cap at 6 to leave margin. Preserves text that's
    # already under the threshold.
    # Long-form (novel/blog) humans use far fewer transitions (d=0.92 gap vs
    # AI). Drop cap target on long text so novel humanize approaches human 2.4
    # density instead of staying at AI's 4.4 baseline.
    cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    trans_target = 3.0 if cn_chars >= 1500 else 6.0
    text = cap_transition_density(text, target=trans_target)

    # Novel/fiction register: strip overused AI-style intensifiers.
    # Spot-check on 20 \u7384\u5e7b samples showed \u300c\u5341\u5206/\u975e\u5e38/\u6781\u5176/\u683c\u5916/\u6781\u4e3a/\u6781\u5ea6/
    # \u5c24\u4e3a/\u9887\u4e3a\u300d+ adj appears ~25-28 times per 20-sample batch as an AI
    # mannerism. Negative lookaheads exclude the two false positives we
    # observed: '\u5341\u5206\u949f' (time noun) and '\u975e\u5e38\u89c4' (adv prefix).
    # Skip '\u65e0\u6bd4' (\u53e5\u5c3e idiomatic, deletion would break clauses) and
    # '\u76f8\u5f53' (quantifier, '\u76f8\u5f53\u591a/\u76f8\u5f53\u957f' \u2260 intensifier).
    if style == 'novel':
        text = re.sub(r'\u5341\u5206(?![\u949f\u4e4b])', '', text)
        text = re.sub(r'\u975e\u5e38(?![\u89c4])', '', text)
        text = re.sub(r'\u6781\u5176', '', text)
        text = re.sub(r'\u683c\u5916', '', text)
        text = re.sub(r'\u6781\u4e3a', '', text)
        text = re.sub(r'\u6781\u5ea6', '', text)
        text = re.sub(r'\u5c24\u4e3a', '', text)
        text = re.sub(r'\u9887\u4e3a', '', text)

    # Clean up artifacts
    text = re.sub(r'[，,]{2,}', '，', text)  # Remove double commas
    text = re.sub(r'[。]{2,}', '。', text)    # Remove double periods
    text = re.sub(r'\n{3,}', '\n\n', text)    # Normalize newlines
    text = re.sub(r'，。', '。', text)          # Remove comma before period
    text = re.sub(r'。，', '。', text)          # Remove period before comma
    
    # ── Final verification loop (stats-optimized) ──
    # If perplexity is still too low, do a targeted second pass on worst sentences
    if _USE_STATS and ngram_analyze:
        stats = ngram_analyze(text)
        ppl = stats.get('perplexity', 0)
        # Threshold: if perplexity is in the "too smooth" zone, try to improve.
        # D-5 (cycle 31): raised 200 → 350 to cover the typical humanized-output
        # perplexity range (~250-300) where indicators still fire.
        if 0 < ppl < 350 and len(text) >= 100:
            sentences = re.split(r'([。！？])', text)
            # Score each sentence
            sent_scores = []
            for i in range(0, len(sentences) - 1, 2):
                s = sentences[i]
                if len(s.strip()) < 5:
                    continue
                s_stats = ngram_analyze(s)
                sent_scores.append((i, s_stats.get('perplexity', 0)))
            
            if sent_scores:
                # Sort by perplexity ascending (worst = most predictable first)
                sent_scores.sort(key=lambda x: x[1])
                # Try to improve the worst 20% (at most 5 sentences)
                n_fix = min(5, max(1, len(sent_scores) // 5))
                
                # Use a different random seed for the second pass
                if seed is not None:
                    random.seed(seed + 1)
                
                for idx, _ in sent_scores[:n_fix]:
                    sent = sentences[idx]
                    # Try each replacement on this sentence
                    sorted_phrases = sorted(PLAIN_REPLACEMENTS.keys(), key=len, reverse=True)
                    for phrase in sorted_phrases:
                        if phrase in sent:
                            alternatives = PLAIN_REPLACEMENTS[phrase]
                            if isinstance(alternatives, str):
                                alternatives = [alternatives]
                            best = pick_best_replacement(sent, phrase, alternatives)
                            sentences[idx] = sent.replace(phrase, best, 1)
                            break  # one fix per sentence to avoid over-rewriting
                
                text = ''.join(sentences)
    
    return text.strip()

# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description='中文 AI 文本人性化 v2.0')
    parser.add_argument('file', nargs='?', help='输入文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--scene', default='general',
                       choices=['general', 'social', 'tech', 'formal', 'chat'],
                       help='场景 (default: general)')
    parser.add_argument('--style', help='写作风格 (调用 style_cn.py)')
    parser.add_argument('-a', '--aggressive', action='store_true', help='激进模式')
    parser.add_argument('--seed', type=int, help='随机种子（可复现）')
    parser.add_argument('--best-of-n', type=int, default=DEFAULT_BEST_OF_N, metavar='N',
                        help=f'运行 N 次 humanize 取 LR 分数最低的那次（默认 {DEFAULT_BEST_OF_N}，N 倍延迟，0 关闭）')
    parser.add_argument('--no-stats', action='store_true',
                       help='跳过统计优化（困惑度反馈），回退到纯规则替换')
    parser.add_argument('--no-noise', action='store_true',
                       help='跳过噪声策略（句长随机化 + 噪声表达插入）')
    parser.add_argument('--quick', action='store_true',
                       help='快速模式（= --no-stats --no-noise），只跑短语替换 + 结构清理')
    parser.add_argument('--cilin', action='store_true',
                       help='用 CiLin 同义词词林扩展候选（~40K 词 vs 手工 200 词）')

    args = parser.parse_args()

    # Toggle stats optimization
    global _USE_STATS
    _USE_STATS = not (args.no_stats or args.quick)

    # Toggle noise strategies
    global _USE_NOISE
    _USE_NOISE = not (args.no_noise or args.quick)

    # Toggle CiLin expansion
    global _USE_CILIN
    _USE_CILIN = args.cilin
    
    # Read input
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except FileNotFoundError:
            print(f'错误: 文件未找到 {args.file}', file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.stdin.read()
    
    if not text.strip():
        print('错误: 输入为空', file=sys.stderr)
        sys.exit(1)
    
    # Humanize
    result = humanize(text, args.scene, args.aggressive, args.seed,
                       best_of_n=args.best_of_n)
    
    # Apply style if specified
    if args.style:
        import subprocess
        style_script = os.path.join(SCRIPT_DIR, 'style_cn.py')
        
        if os.path.exists(style_script):
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
                tmp.write(result)
                tmp_path = tmp.name
            
            try:
                proc = subprocess.run(
                    ['python3', style_script, tmp_path, '--style', args.style],
                    capture_output=True, text=True, encoding='utf-8'
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    result = proc.stdout
                else:
                    print(f'警告: 风格转换失败: {proc.stderr}', file=sys.stderr)
            finally:
                os.unlink(tmp_path)
        else:
            print(f'警告: 未找到风格转换脚本', file=sys.stderr)
    
    # Output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        style_info = f' (风格: {args.style})' if args.style else ''
        scene_info = f' (场景: {args.scene})'
        print(f'✓ 已保存到 {args.output}{scene_info}{style_info}')
    else:
        print(result)

if __name__ == '__main__':
    main()
