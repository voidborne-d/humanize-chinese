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
    """从多个候选替换中选 perplexity 最高的（最不可预测 = 最像人写的）。
    当 _USE_STATS 关闭、ngram_analyze 不可用、或只有单候选时回退到 random.choice。"""
    if not _USE_STATS or not ngram_analyze or len(candidates) <= 1:
        return random.choice(candidates)

    best_candidate = candidates[0]
    best_ppl = 0

    for candidate in candidates:
        new_sentence = sentence.replace(old, candidate, 1)
        stats = ngram_analyze(new_sentence)
        ppl = stats.get('perplexity', 0)
        if ppl > best_ppl:
            best_ppl = ppl
            best_candidate = candidate

    return best_candidate


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
    '因此': ['所以', '因而', '为此', '故而'],
    '然而': ['不过', '但', '可是', '只是'],
    '但是': ['不过', '可是', '只是', '然而'],
    '虽然': ['尽管', '即便', '就算', '纵然'],
    '所以': ['因此', '因而', '故而', '于是'],
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
    '发展': ['推进', '进展', '演进', '推动'],
    '影响': ['波及', '冲击', '左右', '触动'],
    '研究': ['探究', '考察', '审视', '钻研'],
    '表明': ['显示', '说明', '反映', '揭示'],
    '认为': ['觉得', '以为', '判断', '主张'],
    '需要': ['有必要', '须', '要', '得'],
    '使用': ['运用', '采用', '用', '动用'],
    '具有': ['带有', '兼具', '拥有', '含有'],
    '导致': ['引发', '造成', '招致', '引起'],
    '提供': ['给出', '供给', '拿出', '呈上'],
    '分析': ['剖析', '解读', '拆解', '审视'],
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
    '改变': ['改动', '变更', '扭转', '调整'],
    '选择': ['挑选', '择取', '选用', '拣'],
    '支持': ['撑持', '扶持', '相挺', '力挺'],
    '组成': ['构成', '拼成', '组合', '凑成'],
    '形成': ['催生', '铸成', '生成', '酿成'],
    '获得': ['取得', '赢得', '得到', '揽获'],
    '确定': ['敲定', '锁定', '明确', '定下'],
    '发现': ['察觉', '觉察', '识破', '看出'],
    '推动': ['驱动', '助推', '催动', '拉动'],
    '加强': ['强化', '增强', '夯实', '巩固'],
    '体现': ['彰显', '凸显', '映射', '折射'],
    '满足': ['达到', '契合', '符合', '迎合'],
    '存在': ['有', '潜伏', '隐含', '客观上有'],
    '属于': ['归属', '算是', '属', '归入'],
    '考虑': ['斟酌', '权衡', '琢磨', '思量'],
    '处理': ['打理', '应对', '料理', '处置'],
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
    '采用': ['选用', '沿用', '取用', '引用'],
    # ── 副词 / 程度 ──
    '目前': ['眼下', '当前', '现阶段', '如今'],
    '同时': ['与此同时', '此外', '另外', '并且'],
    '通过': ['借助', '凭借', '经由', '依靠'],
    '根据': ['按照', '依据', '参照', '依照'],
    '有效': ['管用', '奏效', '见效', '起作用'],
    '基于': ['立足于', '依托', '以…为基础', '仰赖'],
    '对于': ['针对', '就', '关于', '面对'],
    '非常': ['极其', '十分', '很', '格外'],
    '已经': ['早已', '业已', '已', '早就'],
    '完全': ['彻底', '全然', '纯粹', '压根'],
    '不断': ['持续', '始终', '一再', '反复'],
    '逐渐': ['渐渐', '慢慢', '一步步', '日渐'],
    '主要': ['核心', '关键', '首要', '最要紧的'],
    '一般': ['通常', '往常', '照例', '大抵'],
    '大量': ['海量', '大批', '众多', '成堆的'],
    '进一步': ['更', '再', '深入', '继续'],
    '充分': ['尽情', '透彻', '淋漓', '饱满'],
    '直接': ['径直', '当面', '立刻', '干脆'],
    '特别': ['尤其', '格外', '极', '分外'],
    '一定': ['某种', '相当', '一些', '多少'],
    '必须': ['得', '务必', '非得', '须'],
    '可能': ['也许', '兴许', '或许', '大概'],
    # ── 名词 / 概念 ──
    '重要': ['关键', '核心', '要紧', '紧要'],
    '显著': ['明显', '突出', '可观', '醒目'],
    '问题': ['难题', '困境', '麻烦', '症结'],
    '方面': ['层面', '维度', '角度', '面向'],
    '情况': ['状况', '形势', '境况', '局面'],
    '特点': ['特征', '属性', '标志', '特色'],
    '方法': ['办法', '手段', '途径', '招数'],
    '过程': ['历程', '进程', '流程', '经过'],
    '结果': ['后果', '成果', '产物', '结局'],
    '条件': ['前提', '条件', '要件', '门槛'],
    '作用': ['功用', '效用', '效能', '功能'],
    '内容': ['要素', '成分', '要点', '素材'],
    '程度': ['幅度', '力度', '地步', '深浅'],
    '原因': ['缘由', '根源', '起因', '来由'],
    '目标': ['目的', '指向', '靶心', '方向'],
    '水平': ['档次', '层次', '段位', '高度'],
    '范围': ['领域', '地带', '区间', '覆盖面'],
    '趋势': ['走向', '苗头', '势头', '倾向'],
    '能力': ['本事', '实力', '功底', '才干'],
    '优势': ['长处', '强项', '亮点', '好处'],
    '资源': ['资产', '家底', '储备', '本钱'],
    '环境': ['氛围', '生态', '场景', '背景'],
    '系统': ['体系', '架构', '框架'],
    '策略': ['打法', '路线', '方案', '对策'],
}

# ═══════════════════════════════════════════════════════════════════
#  Strategy 3: Noise expression injection — expression table
# ═══════════════════════════════════════════════════════════════════

NOISE_EXPRESSIONS = {
    'hedging': ['说实话', '坦白讲', '客观地说', '实事求是地讲', '平心而论',
                '老实说', '不夸张地说', '公正地看'],
    'self_correction': ['或者说', '准确地讲', '换个角度看', '严格来说',
                        '更确切地说', '往深了讲', '细想一下'],
    'uncertainty': ['大概', '差不多', '似乎', '或许', '多少有些',
                    '约莫', '估摸着', '八成'],
    'transition_casual': ['话说回来', '反过来看', '换句话说', '说到这里',
                          '再往下想', '回过头看', '顺着这个思路'],
    'filler': ['当然了', '其实', '说到底', '怎么说呢', '不瞒你说',
               '你别说', '讲真', '这么说吧'],
    'personal': ['我觉得', '在我看来', '依我之见', '以我的经验',
                 '在我的理解里', '就我所知', '我个人倾向于'],
}

# Academic-safe categories (no oral fillers or personal opinions)
NOISE_ACADEMIC_CATEGORIES = ['hedging', 'self_correction', 'uncertainty']
# Academic-specific hedging (more formal)
NOISE_ACADEMIC_EXPRESSIONS = {
    'hedging': ['客观地说', '实事求是地讲', '平心而论', '公正地看'],
    'self_correction': ['准确地讲', '严格来说', '更确切地说', '往深了讲'],
    'uncertainty': ['大致', '似乎', '或许', '多少', '在一定程度上'],
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


def reduce_high_freq_bigrams(text, strength=0.3):
    """
    策略1: 扫描文本中的高频 bigram，尝试用低频同义替换降低可预测性。
    strength: 0-1，控制替换比例。
    
    使用基于词的替换（非位置），避免长度变化导致的错位问题。
    """
    bigram_freq = _load_bigram_freq()
    if not bigram_freq:
        return _simple_synonym_pass(text, strength)

    chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chars) < 4:
        return text

    # Step 1: Score each WORD_SYNONYMS word by its surrounding bigram frequency
    word_scores = []  # (word, total_bigram_freq, count_in_text)
    for word in WORD_SYNONYMS:
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

        candidates = WORD_SYNONYMS[word]

        # Pick the candidate with lowest bigram frequency
        best_candidate = candidates[0]
        best_freq = float('inf')

        for candidate in candidates:
            cand_chars = re.findall(r'[\u4e00-\u9fff]', candidate)
            if not cand_chars:
                continue
            total_f = 0
            for i in range(len(cand_chars) - 1):
                total_f += bigram_freq.get(cand_chars[i] + cand_chars[i + 1], 0)
            if total_f < best_freq:
                best_freq = total_f
                best_candidate = candidate

        # Replace all occurrences of this word (use sentinel to avoid chains)
        SENTINEL = '\x00'
        protected = SENTINEL.join(best_candidate)
        text = text.replace(word, protected)
        replaced_words.add(word)

        # Also mark synonyms of the same word to avoid replacing the replacement
        for syn in candidates:
            if syn != best_candidate and syn in WORD_SYNONYMS:
                replaced_words.add(syn)

    # Strip sentinels
    text = text.replace('\x00', '')

    return text


def _simple_synonym_pass(text, strength=0.3):
    """Fallback: replace a fraction of WORD_SYNONYMS matches randomly."""
    found = []
    for word in WORD_SYNONYMS:
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
        candidate = random.choice(WORD_SYNONYMS[word])
        text = text[:pos] + candidate + text[pos + len(word):]
        for p in range(pos, pos + len(candidate)):
            replaced_positions.add(p)
    return text


# ═══════════════════════════════════════════════════════════════════
#  Strategy 2: Sentence length randomization
# ═══════════════════════════════════════════════════════════════════

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
            # Merge if combined length reasonable (< 100 chars)
            if cn_len + cn_len2 < 100:
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

def inject_noise_expressions(text, density=0.15, style='general'):
    """
    策略3: 在句子间或句中适当位置插入噪声表达。
    density: 大约每多少句插入一个（0.15 ≈ 每 6-7 句一个）
    style: general / academic
    """
    if style == 'academic':
        categories = NOISE_ACADEMIC_CATEGORIES
        expressions = NOISE_ACADEMIC_EXPRESSIONS
    else:
        categories = list(NOISE_EXPRESSIONS.keys())
        expressions = NOISE_EXPRESSIONS

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

    injected = 0
    for i in range(len(sentences)):
        # Skip the last sentence (avoid orphaned expressions)
        if i >= len(sentences) - 1:
            continue
        # Skip very short sentences
        s_text = sentences[i][0]
        if len(re.findall(r'[\u4e00-\u9fff]', s_text)) < 8:
            continue
        if random.random() > density:
            continue

        cat = random.choice(categories)
        expr_list = expressions.get(cat, [])
        if not expr_list:
            continue
        expr = random.choice(expr_list)

        s, p = sentences[i]

        # Decide insertion position
        if cat in ('hedging', 'filler', 'personal', 'transition_casual'):
            # Insert at sentence beginning
            s = expr + '，' + s.lstrip()
        elif cat in ('self_correction', 'uncertainty'):
            # Insert mid-sentence at a comma
            comma_pos = s.find('，')
            if comma_pos > 3:
                s = s[:comma_pos + 1] + expr + '，' + s[comma_pos + 1:]
            else:
                s = expr + '，' + s.lstrip()

        sentences[i] = [s, p]
        injected += 1

    return ''.join(s + p for s, p in sentences)


# ─── Core Transforms ───

def remove_three_part_structure(text):
    """Remove 首先/其次/最后, 第一/第二/第三 patterns"""
    # Don't just delete — replace with natural transitions
    replacements = [
        (r'首先[，,]\s*', ''),
        (r'其次[，,]\s*', lambda m: random.choice(['再说，', '另外，', ''])),
        (r'最后[，,]\s*', lambda m: random.choice(['还有，', '最后说一点，', ''])),
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
                    part = part[:match.start()] + replacement + part[match.end():]
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
            # Find the sentence containing this phrase for stats-optimized selection
            # Use pick_best_replacement to choose the highest-perplexity candidate
            replacement = pick_best_replacement(text, phrase, alternatives)
            text = text.replace(phrase, replacement, 1)  # Replace first occurrence
            # For subsequent occurrences, use different alternatives
            while phrase in text:
                replacement = pick_best_replacement(text, phrase, alternatives)
                text = text.replace(phrase, replacement, 1)
    
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
            
            if split_points:
                # Split at the most central point
                mid = len(sent) // 2
                best = min(split_points, key=lambda x: abs(x[0] - mid))
                part1 = sent[:best[0]]
                part2 = sent[best[0]+1:]  # Skip the comma
                result.append(part1 + '。' + part2 + punct)
            else:
                # Split at a comma near the middle
                commas = [m.start() for m in re.finditer(r'[，,]', sent)]
                if commas:
                    mid = len(sent) // 2
                    best_comma = min(commas, key=lambda x: abs(x - mid))
                    part1 = sent[:best_comma]
                    part2 = sent[best_comma+1:]
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
    
    lengths = [len(p) for p in paragraphs]
    avg_len = sum(lengths) / len(lengths) if lengths else 100
    
    result = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        
        # Randomly merge short adjacent paragraphs
        if (i + 1 < len(paragraphs) and
            len(para) < avg_len * 0.6 and
            len(paragraphs[i + 1]) < avg_len * 0.6 and
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
        '提供': ['给出', '带来', '拿出'],
        '具有': ['有', '拥有', '带有'],
        '进一步': ['更', '再', '深入'],
        '不断': ['持续', '一直', '始终'],
        '有效': ['管用', '见效', '奏效'],
        '积极': ['主动', '热心'],
        '促进': ['推动', '带动'],
        '加强': ['强化', '增强'],
        '提高': ['提升', '增加'],
        '重要': ['关键', '核心'],
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

def humanize(text, scene='general', aggressive=False, seed=None):
    """Apply all humanization transformations in order"""
    if seed is not None:
        random.seed(seed)
    
    config = SCENES.get(scene, SCENES['general'])
    casualness = config.get('casualness', 0.3)
    if aggressive:
        casualness = min(1.0, casualness + 0.3)
    
    # Pass 1: Structure cleanup
    text = remove_three_part_structure(text)
    text = replace_phrases(text, casualness)
    
    # Pass 2: Deep sentence restructuring (句级改写)
    try:
        from restructure_cn import deep_restructure
    except ImportError:
        try:
            from scripts.restructure_cn import deep_restructure
        except ImportError:
            deep_restructure = None
    if deep_restructure:
        text = deep_restructure(text, aggressive=aggressive)

    # Pass 2b: Sentence merge/split (original)
    if config.get('merge_short', False):
        text = merge_short_sentences(text)
    if config.get('split_long', False):
        text = split_long_sentences(text)
    
    # Pass 3: Rhythm and variety
    text = reduce_punctuation(text)
    text = diversify_vocabulary(text)
    
    if config.get('rhythm_variation', False):
        text = vary_paragraph_rhythm(text)
    
    # Pass 4: Scene-specific
    if config.get('add_casual', False) or aggressive:
        text = add_casual_expressions(text, casualness)
    
    if config.get('shorten_paragraphs', False):
        text = shorten_paragraphs(text)
    
    # ── NEW: Three perplexity-boosting strategies ──
    
    # Strategy 1: Low-frequency bigram injection (always active)
    bigram_strength = 0.5 if aggressive else 0.3
    text = reduce_high_freq_bigrams(text, strength=bigram_strength)
    
    # Strategy 2 & 3: Noise injection (skipped with --no-noise)
    if _USE_NOISE:
        # Strategy 3: Noise expression injection
        noise_density = 0.25 if aggressive else 0.15
        text = inject_noise_expressions(text, density=noise_density, style='general')
        
        # Strategy 2: Sentence length randomization
        text = randomize_sentence_lengths(text, aggressive=aggressive, seed=seed)
    
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
        # Threshold: if perplexity is in the "too smooth" zone, try to improve
        if 0 < ppl < 200 and len(text) >= 100:
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
    parser.add_argument('--no-stats', action='store_true',
                       help='跳过统计优化（困惑度反馈），回退到纯规则替换')
    parser.add_argument('--no-noise', action='store_true',
                       help='跳过噪声策略（句长随机化 + 噪声表达插入）')
    
    args = parser.parse_args()
    
    # Toggle stats optimization
    global _USE_STATS
    _USE_STATS = not args.no_stats
    
    # Toggle noise strategies
    global _USE_NOISE
    _USE_NOISE = not args.no_noise
    
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
    result = humanize(text, args.scene, args.aggressive, args.seed)
    
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
