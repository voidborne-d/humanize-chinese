#!/usr/bin/env python3
"""
Chinese Academic Paper AIGC Detector & Humanizer v1.0
Specialized for Chinese academic papers — targets CNKI/VIP/Wanfang AIGC detection patterns.
Features: 10 detection dimensions, 100+ replacement rules, hedging injection, structure variation.
Pure Python, no external dependencies.
"""

import sys
import re
import random
import json
import os
import argparse
from collections import defaultdict
from math import log2

# Import n-gram statistical model
try:
    from ngram_model import analyze_text as ngram_analyze
except ImportError:
    try:
        from scripts.ngram_model import analyze_text as ngram_analyze
    except ImportError:
        ngram_analyze = None

# Import general detector so --compare can show both academic and general AIGC scores.
# Users comparing to CNKI/VIP-style detectors care about the general score, not the
# academic-specific weighted one.
try:
    from detect_cn import detect_patterns as _general_detect
    from detect_cn import calculate_score as _general_score
except ImportError:
    try:
        from scripts.detect_cn import detect_patterns as _general_detect
        from scripts.detect_cn import calculate_score as _general_score
    except ImportError:
        _general_detect = None
        _general_score = None


def _compute_general_score(text):
    """Run general detect_cn on text, return (score, issues, metrics) or (None, None, None)."""
    if _general_detect is None or _general_score is None:
        return None, None, None
    g_issues, g_metrics = _general_detect(text)
    g_score = _general_score(g_issues, g_metrics)
    return g_score, g_issues, g_metrics

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERNS_FILE = os.path.join(SCRIPT_DIR, 'patterns_cn.json')


def load_config():
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


CONFIG = load_config()
ACAD = CONFIG.get('academic_patterns', {}) if CONFIG else {}

# ═══════════════════════════════════════════════════════════════════
#  Detection Patterns — 10 Dimensions
# ═══════════════════════════════════════════════════════════════════

# --- 1. AI 典型学术措辞 ---
AI_ACADEMIC_PHRASES = ACAD.get('ai_academic_phrases', {}).get('phrases', [
    '本文旨在', '研究表明', '具有重要意义', '进行了深入分析',
    '具有重要的理论意义和实践价值', '为此本文', '鉴于此',
    '对此进行了系统的', '进行了全面的分析', '进行了系统的研究',
    '取得了显著的成效', '具有广阔的应用前景', '发挥着重要作用',
    '引起了广泛关注', '得到了广泛的应用', '提供了有力的支撑',
    '提出了切实可行的', '进行了有益的探索', '奠定了坚实的基础',
    '提供了重要的参考价值', '提供了新的思路', '开辟了新的途径',
    '进行了详细的阐述', '做出了重要贡献', '具有一定的参考价值',
    '受到了学术界的广泛关注', '成为学术界研究的热点',
    '具有十分重要的现实意义', '有着不可忽视的作用',
    '对其进行深入研究', '有待进一步研究',
])

# --- 2. 过度被动句式 ---
PASSIVE_PATTERNS = ACAD.get('passive_patterns', {}).get('regex', [
    r'被广泛(应用|使用|采用|运用|关注|认可|接受)',
    r'被认为是',
    r'被(视为|看作|称为|誉为)',
    r'被(普遍|学界|学术界|研究者)(认为|接受|采纳)',
    r'被(充分|有效|合理)(利用|运用|开发)',
    r'被(证明|证实|验证)(为|是)',
    r'受到了?(广泛|高度|普遍|学界的?)(关注|重视|认可)',
])

# --- 3. 段落结构整齐度 ---
# (检测逻辑：每段首句总述 + N 个分论点 + 总结)
PARAGRAPH_OPENER_PATTERNS = [
    r'^(总的来看|总体而言|概括来说|从总体上看)',
    r'^(在\S{2,8}方面)',
    r'^(就\S{2,8}而言)',
    r'^(关于\S{2,8}(的问题|方面|层面))',
    r'^(从\S{2,8}(角度|视角|层面)(来看|来说|出发))',
]

# --- 4. 逻辑连接词 ---
LOGIC_CONNECTORS = ACAD.get('logic_connectors', {}).get('phrases', [
    '因此', '所以', '由此可见', '综上所述', '总而言之',
    '此外', '另外', '与此同时', '不仅如此', '更重要的是',
    '换言之', '也就是说', '具体而言', '进而', '从而',
    '然而', '但是', '不过', '尽管如此', '相比之下',
    '一方面', '另一方面', '首先', '其次', '最后',
    '事实上', '实际上', '显然', '毫无疑问', '值得注意的是',
    '需要指出的是', '值得一提的是', '由此', '基于此',
])

# --- 5. 同义表达匮乏 --- (检测逻辑在函数中)

# --- 6. 引用整合度 ---
CITATION_TEMPLATES = ACAD.get('citation_templates', {}).get('regex', [
    r'[（(]\d{4}[）)]指出',
    r'[（(]\d{4}[）)]认为',
    r'[（(]\d{4}[）)]的研究(表明|发现|指出|证实)',
    r'根据\S{1,6}[（(]\d{4}[）)]的研究',
    r'正如\S{1,6}[（(]\d{4}[）)]所(指出|述|言)',
    r'\S{1,6}等[（(]\d{4}[）)](的研究)?(表明|发现|认为)',
])

# --- 7. 数据论述模板化 ---
DATA_TEMPLATES = ACAD.get('data_templates', {}).get('phrases', [
    '数据显示', '数据表明', '从表中可以看出', '如表所示',
    '从图中可以看出', '如图所示', '由表可知', '由图可知',
    '根据表中数据', '从上表可以看出', '通过数据分析可知',
    '统计结果表明', '分析结果显示', '实验结果表明',
    '调查结果显示', '从数据中不难发现', '数据分析结果表明',
    '表中数据表明', '从图表中可以清晰地看出',
])

# --- 8. 过度列举 ---
ENUMERATION_REGEX = [
    r'(?:(?:①|②|③|④|⑤|⑥).*?[。；;]){3,}',
    r'(?:(?:第[一二三四五六七八九十])[，,].*?[。；;]){3,}',
    r'(?:(?:\([一二三四五六]\)).*?[。；;]){3,}',
    r'(?:(?:\d\.)\s*.*?[。；;]){4,}',
]

# --- 9. 结论过于圆满（缺少局限性） ---
PERFECT_CONCLUSION_PHRASES = ACAD.get('perfect_conclusion', {}).get('phrases', [
    '取得了显著成效', '取得了丰硕成果', '取得了重大突破',
    '圆满完成', '成效显著', '效果明显', '成果丰硕',
    '为.*?提供了有力支撑', '为.*?奠定了坚实基础',
    '具有重要的理论意义和实践价值', '前景广阔',
])
LIMITATION_MARKERS = [
    '局限', '不足', '有待', '仍需', '尚未', '尚需',
    '未来研究', '后续研究', '进一步探讨', '存在一定的',
    '样本量', '推广性', '外部效度', '内部效度',
]

# --- 10. 语气过于确定 ---
CERTAINTY_MARKERS = ACAD.get('certainty_markers', {}).get('phrases', [
    '必然', '一定会', '毫无疑问', '无疑', '显然',
    '毋庸置疑', '不可否认', '确定无疑', '势必',
    '必将', '注定', '无一例外', '绝对',
])
HEDGING_MARKERS = [
    '可能', '或许', '也许', '在一定条件下', '在某种程度上',
    '一般而言', '通常', '大致', '似乎', '倾向于',
    '有可能', '在一定范围内', '初步', '大体上',
]


# ═══════════════════════════════════════════════════════════════════
#  Utility
# ═══════════════════════════════════════════════════════════════════

def count_chinese(text):
    return len(re.findall(r'[\u4e00-\u9fff]', text))


def split_sentences(text):
    parts = re.split(r'([。！？\n])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        if s:
            sentences.append(s + (parts[i + 1] if i + 1 < len(parts) else ''))
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return [s for s in sentences if len(s) > 1]


def char_entropy(text):
    chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chars) < 10:
        return 5.0
    bigrams = defaultdict(int)
    for i in range(len(chars) - 1):
        bigrams[chars[i] + chars[i + 1]] += 1
    total = sum(bigrams.values())
    if total == 0:
        return 5.0
    entropy = 0
    for count in bigrams.values():
        p = count / total
        if p > 0:
            entropy -= p * log2(p)
    return entropy


def topic_diffusion(text):
    """
    扩散度: measures how much topic content shifts across paragraphs.

    Implementation: for each paragraph, extract top-20 bigrams as its topic
    signature. Compute mean Jaccard similarity between consecutive paragraphs.
    Diffusion = 1 - mean_similarity.

    Interpretation:
      - Low diffusion (< 0.3): topics repeat heavily across paragraphs
        → template-y / AI-generated "elaborate the same point 5 times" pattern
      - High diffusion (> 0.7): topics shift naturally → human-like

    Returns tuple (diffusion_score, n_paragraphs_used).
    """
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 20]
    if len(paragraphs) < 2:
        return 1.0, len(paragraphs)

    def signature(para):
        chars = re.findall(r'[\u4e00-\u9fff]', para)
        if len(chars) < 10:
            return set()
        bigrams = {}
        for i in range(len(chars) - 1):
            bg = chars[i] + chars[i + 1]
            bigrams[bg] = bigrams.get(bg, 0) + 1
        # Top-20 by frequency
        top = sorted(bigrams.items(), key=lambda x: -x[1])[:20]
        return {bg for bg, _ in top}

    sigs = [signature(p) for p in paragraphs]
    sigs = [s for s in sigs if s]
    if len(sigs) < 2:
        return 1.0, len(sigs)

    # Mean Jaccard similarity across consecutive paragraph pairs
    sims = []
    for i in range(len(sigs) - 1):
        a, b = sigs[i], sigs[i + 1]
        union = a | b
        inter = a & b
        if not union:
            continue
        sims.append(len(inter) / len(union))
    if not sims:
        return 1.0, len(sigs)
    mean_sim = sum(sims) / len(sims)
    return 1.0 - mean_sim, len(sigs)


# ═══════════════════════════════════════════════════════════════════
#  Detection Engine — 10 Dimensions
# ═══════════════════════════════════════════════════════════════════

DIMENSION_WEIGHTS = {
    'ai_academic_phrases':   8,   # AI 典型学术措辞
    'passive_overuse':       5,   # 被动句式过度
    'paragraph_uniformity':  6,   # 段落结构过于整齐
    'connector_density':     7,   # 逻辑连接词密度
    'synonym_poverty':       6,   # 同义表达匮乏
    'citation_integration':  4,   # 引用整合度低
    'data_template':         5,   # 数据论述模板化
    'over_enumeration':      5,   # 过度列举
    'perfect_conclusion':    6,   # 结论过于圆满
    'certainty_overuse':     7,   # 语气过于确定
    'low_topic_diffusion':   5,   # 扩散度低（知网 5 维之一）
    # Statistical dimensions (n-gram perplexity)
    'stat_low_perplexity':   0,   # scored separately
    'stat_low_burstiness':   0,   # scored separately
    'stat_uniform_entropy':  0,   # scored separately
}

# Statistical feature weights (contribute up to ~25% of final score)
STATISTICAL_WEIGHTS = {
    'stat_low_sentence_length_cv': 14,        # HC3 d=1.22 (cycle 5)
    'stat_low_short_sentence_fraction': 12,   # HC3 d=1.21 (cycle 5)
    'stat_low_perplexity': 12,
    'stat_low_burstiness': 10,
    'stat_low_comma_density': 8,              # HC3 d=-0.47 (cycle 7)
    'stat_uniform_entropy': 8,
}


def detect_academic(text):
    """Run all 10 academic AIGC detection dimensions."""
    issues = defaultdict(list)
    char_count = count_chinese(text)
    sentences = split_sentences(text)
    paragraphs = [p.strip() for p in text.split('\n') if p.strip() and len(p.strip()) > 10]

    # ── 1. AI 典型学术措辞 ──
    for phrase in AI_ACADEMIC_PHRASES:
        cnt = text.count(phrase)
        if cnt > 0:
            issues['ai_academic_phrases'].append({
                'text': phrase, 'count': cnt, 'severity': 'critical'})

    # ── 2. 被动句式过度 ──
    passive_total = 0
    for pat in PASSIVE_PATTERNS:
        for m in re.finditer(pat, text):
            passive_total += 1
            if len(issues['passive_overuse']) < 10:
                issues['passive_overuse'].append({
                    'text': m.group()[:40], 'severity': 'high'})
    if passive_total == 0:
        pass  # no issue

    # ── 3. 段落结构整齐度 ──
    if len(paragraphs) >= 3:
        lengths = [count_chinese(p) for p in paragraphs]
        avg = sum(lengths) / len(lengths) if lengths else 1
        if avg > 0:
            cv = (sum((l - avg) ** 2 for l in lengths) / len(lengths)) ** 0.5 / avg
            if cv < 0.18:
                issues['paragraph_uniformity'].append({
                    'text': f'段落长度 CV={cv:.2f}，结构过于整齐',
                    'severity': 'high'})

        # Check for repeating structure: opener pattern similarity
        opener_count = 0
        for p in paragraphs:
            first_sent = p.split('。')[0] if '。' in p else p[:50]
            for pat in PARAGRAPH_OPENER_PATTERNS:
                if re.match(pat, first_sent.strip()):
                    opener_count += 1
                    break
        if opener_count >= 3:
            issues['paragraph_uniformity'].append({
                'text': f'{opener_count} 个段落使用相似的起始结构',
                'severity': 'high'})

    # ── 4. 逻辑连接词密度 ──
    connector_count = 0
    found_connectors = []
    for c in LOGIC_CONNECTORS:
        cnt = text.count(c)
        if cnt > 0:
            connector_count += cnt
            found_connectors.append(c)
    if char_count > 0:
        density = connector_count / (char_count / 100)
        threshold = 3.0  # per 100 chars
        if density > threshold:
            issues['connector_density'].append({
                'text': f'逻辑连接词密度 {density:.1f}/百字（阈值 {threshold}），共 {connector_count} 个',
                'count': connector_count, 'severity': 'high'})
            # show top ones
            for c in found_connectors[:5]:
                issues['connector_density'].append({
                    'text': f'  · {c} ×{text.count(c)}', 'severity': 'info'})

    # ── 5. 同义表达匮乏 ──
    # Find words repeated 3+ times that should have synonyms
    academic_repeat_words = [
        '研究', '分析', '探讨', '论述', '阐述', '表明',
        '发现', '指出', '认为', '提出', '进行', '开展',
        '影响', '作用', '意义', '价值', '问题', '方面',
        '水平', '能力', '效果', '结果', '方法', '策略',
        '措施', '途径', '机制', '模式', '体系', '框架',
    ]
    repeat_issues = []
    for w in academic_repeat_words:
        cnt = text.count(w)
        if cnt >= 4:
            repeat_issues.append((w, cnt))
    repeat_issues.sort(key=lambda x: x[1], reverse=True)
    for w, cnt in repeat_issues[:5]:
        issues['synonym_poverty'].append({
            'text': f'"{w}" 重复 {cnt} 次', 'count': cnt, 'severity': 'medium'})

    # ── 6. 引用整合度低 ──
    cite_template_count = 0
    for pat in CITATION_TEMPLATES:
        for m in re.finditer(pat, text):
            cite_template_count += 1
    # Count total citations
    total_cites = len(re.findall(r'[（(]\d{4}[）)]', text))
    if total_cites >= 3 and cite_template_count >= 3:
        ratio = cite_template_count / total_cites if total_cites > 0 else 0
        if ratio > 0.6:
            issues['citation_integration'].append({
                'text': f'{cite_template_count}/{total_cites} 处引用使用模板化表述（比例 {ratio:.0%}）',
                'severity': 'medium'})

    # ── 7. 数据论述模板化 ──
    for phrase in DATA_TEMPLATES:
        cnt = text.count(phrase)
        if cnt > 0:
            issues['data_template'].append({
                'text': phrase, 'count': cnt, 'severity': 'medium'})

    # ── 8. 过度列举 ──
    for pat in ENUMERATION_REGEX:
        for m in re.finditer(pat, text, re.DOTALL):
            issues['over_enumeration'].append({
                'text': m.group()[:60] + '...', 'severity': 'medium'})

    # ── 9. 结论过于圆满 ──
    # Check last 20% of text for perfect conclusion without limitations
    tail = text[int(len(text) * 0.8):]
    has_limitation = any(m in tail for m in LIMITATION_MARKERS)
    perfect_count = 0
    for phrase in PERFECT_CONCLUSION_PHRASES:
        if re.search(phrase, tail):
            perfect_count += 1
    if perfect_count >= 2 and not has_limitation:
        issues['perfect_conclusion'].append({
            'text': f'结论部分有 {perfect_count} 处圆满表述，且缺少局限性讨论',
            'severity': 'high'})

    # ── 10. 语气过于确定 ──
    certain_count = sum(text.count(w) for w in CERTAINTY_MARKERS)
    hedge_count = sum(text.count(w) for w in HEDGING_MARKERS)
    if char_count > 200:
        if certain_count >= 3 and hedge_count < 2:
            issues['certainty_overuse'].append({
                'text': f'确定性表述 {certain_count} 次，学术留白仅 {hedge_count} 次',
                'severity': 'high'})
        elif certain_count > 0 and hedge_count == 0:
            issues['certainty_overuse'].append({
                'text': f'确定性表述 {certain_count} 次，完全缺少学术犹豫语',
                'severity': 'medium'})

    # ── 11. 扩散度 (topic diffusion across paragraphs — 知网 5 维之一) ──
    # Human academic writing evolves topics; AI text repeats same concepts across
    # paragraphs with only paraphrasing. Low diffusion = stuck on one topic.
    if len(paragraphs) >= 3 and char_count >= 300:
        diffusion, n_used = topic_diffusion(text)
        if n_used >= 3 and diffusion < 0.5:
            issues['low_topic_diffusion'].append({
                'text': f'段落扩散度 {diffusion:.2f}（< 0.5，段间主题重叠过高）',
                'severity': 'medium' if diffusion > 0.35 else 'high'})

    # ── 11. 统计特征：N-gram 困惑度 ──
    ngram_stats = None
    if ngram_analyze and char_count >= 100:
        ngram_stats = ngram_analyze(text)
        indicators = ngram_stats.get('indicators', {})

        if indicators.get('low_perplexity'):
            ppl = ngram_stats['perplexity']
            issues['stat_low_perplexity'].append({
                'text': f'文本困惑度 {ppl:.1f}（学术 AI 文本通常在此范围内）',
                'severity': 'statistical'})

        if indicators.get('low_burstiness'):
            burst = ngram_stats['burstiness']
            issues['stat_low_burstiness'].append({
                'text': f'困惑度变异系数 {burst:.3f}（过于均匀，缺少写作起伏）',
                'severity': 'statistical'})

        if indicators.get('uniform_entropy'):
            ent_cv = ngram_stats['entropy_cv']
            issues['stat_uniform_entropy'].append({
                'text': f'段落熵变异系数 {ent_cv:.3f}（段落间复杂度过于一致）',
                'severity': 'statistical'})

        # Cycle 5 strong indicators — sentence-length burstiness
        if indicators.get('low_sentence_length_cv'):
            sl = ngram_stats.get('sent_len', {})
            issues['stat_low_sentence_length_cv'].append({
                'text': f'句长变异系数 {sl.get("cv", 0):.2f}（句子长度过于均匀）',
                'severity': 'statistical'})

        if indicators.get('low_short_sentence_fraction'):
            sl = ngram_stats.get('sent_len', {})
            issues['stat_low_short_sentence_fraction'].append({
                'text': f'短句占比 {sl.get("short_frac", 0):.1%}（几乎无 10 字以内短句）',
                'severity': 'statistical'})

        # Cycle 7 — low comma density
        if indicators.get('low_comma_density'):
            pc = ngram_stats.get('punct', {})
            issues['stat_low_comma_density'].append({
                'text': f'逗号密度 {pc.get("comma_density", 0):.2f}/百字（句内停顿偏少）',
                'severity': 'statistical'})

    # ── Metrics ──
    entropy = char_entropy(text)
    metrics = {
        'char_count': char_count,
        'sentence_count': len(sentences),
        'paragraph_count': len(paragraphs),
        'entropy': entropy if char_count > 200 else None,
        'connector_density': connector_count / (char_count / 100) if char_count > 0 else 0,
        'passive_count': passive_total,
        'certainty_count': certain_count,
        'hedging_count': hedge_count,
        'citation_count': total_cites,
    }

    # Add statistical metrics if available
    if ngram_stats:
        metrics['perplexity'] = ngram_stats['perplexity']
        metrics['burstiness'] = ngram_stats['burstiness']
        metrics['entropy_cv'] = ngram_stats['entropy_cv']

    return issues, metrics


def calculate_academic_score(issues):
    """Calculate AIGC probability score 0-100 for academic text.
    
    Scoring composition:
      - Rule-based dimensions: ~75% weight
      - Statistical features (perplexity/burstiness/entropy): ~25% weight
    """
    raw = 0
    for dim, items in issues.items():
        # Skip statistical items — scored separately
        if dim.startswith('stat_'):
            continue
        weight = DIMENSION_WEIGHTS.get(dim, 3)
        for item in items:
            sev = item.get('severity', 'medium')
            if sev == 'info':
                continue
            count = item.get('count', 1)
            sev_mult = {'critical': 1.5, 'high': 1.0, 'medium': 0.6, 'low': 0.3}.get(sev, 0.6)
            raw += weight * sev_mult * min(count, 5)
    
    # Rule-based score (cap at 60 — A-path 2026-04-19 cycle 20)
    rule_score = min(60, int(raw * 0.7))

    # Statistical score (cap 40 — raised from 25 after HC3 measurement showed
    # uncapped stat Cohen's d = 1.695, cap=25 was clipping 90% of AI signal).
    stat_score = 0
    for dim, items in issues.items():
        if dim.startswith('stat_') and items:
            stat_score += STATISTICAL_WEIGHTS.get(dim, 5)
    stat_score = min(40, stat_score)

    return min(100, rule_score + stat_score)


def score_to_level(score):
    if score >= 75:
        return 'very_high'
    elif score >= 50:
        return 'high'
    elif score >= 25:
        return 'medium'
    return 'low'


# ═══════════════════════════════════════════════════════════════════
#  Academic Humanization Engine
# ═══════════════════════════════════════════════════════════════════

# Replacement dictionary: AI expression -> list of more natural academic alternatives
ACADEMIC_REPLACEMENTS = ACAD.get('replacements', {})
if not ACADEMIC_REPLACEMENTS:
    ACADEMIC_REPLACEMENTS = {
        # --- AI 典型学术措辞替换 (50+) ---
        '本文旨在': ['本研究聚焦于', '本文着重', '本文尝试'],
        '研究表明': ['已有文献指出', '前人研究发现', '相关研究揭示'],
        '具有重要意义': ['不容忽视', '值得关注', '有其独特价值'],
        '具有重要的理论意义和实践价值': ['兼具理论探索与实践参考的双重价值', '在学理与应用两个层面均有所推进'],
        '进行了深入分析': ['作了较为细致的考察', '做了逐层剖析', '展开了多角度的审视'],
        '进行了全面的分析': ['从多个维度加以考察', '较为系统地做了梳理'],
        '进行了系统的研究': ['围绕该问题做了较为完整的探索', '对此做了逐步推进的研究'],
        '取得了显著的成效': ['收到了一定的效果', '初步达到了预期目标'],
        '具有广阔的应用前景': ['在应用层面仍有可拓展的空间', '其实践潜力有待进一步挖掘'],
        '发挥着重要作用': ['扮演着不可或缺的角色', '在其中起到了关键的支撑'],
        '引起了广泛关注': ['逐渐进入研究者的视野', '日益受到学界的重视'],
        '得到了广泛的应用': ['已在多个领域落地', '实际应用范围持续扩大'],
        '提供了有力的支撑': ['为后续工作铺垫了基础', '在技术层面给予了支持'],
        '提出了切实可行的': ['给出了具有操作性的', '拟定了较为务实的'],
        '进行了有益的探索': ['做了初步的尝试', '在这一方向上迈出了一步'],
        '奠定了坚实的基础': ['打下了一定的基础', '在基础层面做了铺垫'],
        '提供了重要的参考价值': ['对相关研究有所启发', '可为后续研究提供借鉴'],
        '提供了新的思路': ['打开了一个新的切入角度', '在思路上有所创新'],
        '开辟了新的途径': ['探索出一条可能的路径', '尝试了一种新的进路'],
        '进行了详细的阐述': ['做了较为充分的说明', '逐一加以论述'],
        '做出了重要贡献': ['在该领域有所推进', '对这一问题的认识起到了补充作用'],
        '具有一定的参考价值': ['可供后来者参考', '对同领域研究有所帮助'],
        '受到了学术界的广泛关注': ['近年来已成为学界讨论的议题之一'],
        '成为学术界研究的热点': ['在学界引发了持续的讨论'],
        '具有十分重要的现实意义': ['对当下的实际问题有着直接的观照意义'],
        '有着不可忽视的作用': ['其作用不宜低估', '在其中发挥着不小的影响'],
        '对其进行深入研究': ['对此做进一步的追问', '就此展开更细致的考察'],
        '有待进一步研究': ['仍有继续追问的空间', '后续尚可深入'],
        '鉴于此': ['基于上述考虑', '考虑到这一背景'],
        '为此本文': ['在此基础上，本文', '因此本文尝试'],

        # --- 被动句式替换 (15+) ---
        '被广泛应用于': ['已广泛运用于', '广泛用于'],
        '被广泛应用': ['已在多个场景中得到使用', '使用范围较广'],
        '被广泛使用': ['使用颇为普遍', '在实际中频繁出现'],
        '被广泛采用': ['已为多数研究者所采纳', '采用率较高'],
        '被广泛关注': ['持续吸引着研究者的目光', '关注度逐年上升'],
        '被认为是': ['一般视为', '通常归入', '多看作'],
        '被视为': ['常被看作', '往往归类为'],
        '被看作': ['通常被理解为', '多半被归为'],
        '被称为': ['学界习惯称之为', '一般称其为'],
        '被普遍认为': ['多数学者倾向于认为', '主流观点认为'],
        '被证明': ['经验证', '已有证据支持'],
        '被证实': ['得到了实证支持', '验证结果支持'],
        '受到了广泛关注': ['引发了较多讨论', '获得了较高的关注度'],
        '受到了高度重视': ['得到了相当程度的重视'],

        # --- 数据论述替换 (18+) ---
        '数据显示': ['从数据来看', '数据层面反映出', '统计数字指向'],
        '数据表明': ['数据所呈现的趋势是', '对数据的解读提示'],
        '从表中可以看出': ['观察该表', '表中所列数据反映出', '对比表中各列'],
        '如表所示': ['参见下表', '该表汇总了', '以下表格列出了'],
        '从图中可以看出': ['对照该图', '图中曲线显示', '观察图形走势'],
        '如图所示': ['参见下图', '图中呈现的规律是'],
        '由表可知': ['该表揭示了', '梳理表中数据后发现'],
        '由图可知': ['图形走势反映出', '从该图可以初步判断'],
        '根据表中数据': ['依据表内数据', '结合表中各项指标'],
        '从上表可以看出': ['上表所列数据提示', '回顾上表'],
        '通过数据分析可知': ['经过数据梳理后发现', '对数据做初步分析后'],
        '统计结果表明': ['统计分析给出的结论是', '数据的统计特征指向'],
        '分析结果显示': ['分析结果提示', '根据分析输出'],
        '实验结果表明': ['实验所得结果指向', '从实验数据来看'],
        '调查结果显示': ['问卷反馈汇总后发现', '受访者的回答反映出'],
        '从数据中不难发现': ['稍加留意便可发现', '数据中隐含着'],
        '数据分析结果表明': ['对数据做深入分析后的结论是'],
        '从图表中可以清晰地看出': ['图表较为直观地呈现了'],

        # --- 逻辑连接词柔化 (20+) ---
        '综上所述': ['回顾以上讨论', '梳理上文的论述'],
        '总而言之': ['概括地说', '归结起来'],
        '由此可见': ['从这一点延伸来看', '这也提示我们'],
        '不难发现': ['稍加留意便可发现', '细看之下'],
        '值得注意的是': ['需要留意的一点是', '这里有一个值得关注的细节'],
        '需要指出的是': ['这里需要做一个说明', '有必要补充的是'],
        '值得一提的是': ['此外还有一个值得提及的细节', '顺便一提'],
        '不仅如此': ['除此之外', '在此基础上还'],
        '与此同时': ['同一时期', '在此过程中'],
        '在此基础上': ['以此为起点', '在上述结论的延长线上'],
        '毫无疑问': ['应当承认', '较为确定的是'],
        '事实上': ['实际情况是', '就实际而言'],
        '显而易见': ['较为明显的是', '比较直观的一点是'],
        '不可否认': ['应当承认', '确实'],
        '更重要的是': ['更关键的一层是', '进一步说'],
        '换言之': ['换一种表述', '用另一种方式理解'],
        '具体而言': ['展开来说', '逐一来看'],
        '此外': ['另外还有', '除上述之外'],
        '进而': ['由此推进', '在此基础上进一步'],
        '从而': ['进而使得', '以此达到'],
        '基于此': ['出于这一考虑', '以此为出发点'],
        '总的来说': ['整体看来', '从宏观上概括'],

        # --- 确定性语气柔化 (10+) ---
        '必然会': ['很可能会', '大概率会'],
        '必然': ['大概率', '在多数情况下'],
        '一定会': ['很可能会', '大概率将'],
        '毫无疑问': ['应当承认', '较为确定的是'],
        '无疑': ['在很大程度上', '应当说'],
        '毋庸置疑': ['较为明确的是', '可以说'],
        '确定无疑': ['在现有证据下可以认为', '目前的结论倾向于'],
        '势必': ['很可能', '有较大概率'],
        '必将': ['预计将', '有望'],
        '注定': ['大概率会', '从趋势看可能'],
        '无一例外': ['在绝大多数情况下', '几乎所有案例中'],
        '绝对': ['在很大程度上', '基本上'],
        '显然': ['从现有资料来看', '比较明确的是'],

        # --- 模板句式替换 (10+) ---
        '随着社会的不断发展': ['近年来社会变迁加速', '在社会持续演进的过程中'],
        '在当今社会': ['当前', '在眼下的社会语境中'],
        '在当今时代': ['当下', '就当前阶段而言'],
        '具有重要的现实意义': ['对当下的问题有着切实的回应', '与当前的现实需求直接相关'],
        '本文主要研究': ['本文聚焦的问题是', '本文所考察的对象是'],
        '本文的研究目的': ['本文试图解答的问题', '本文关心的核心议题'],
    }

# Hedging expressions to inject (only multi-char phrases that read well between commas)
# Module-level flag: whether to use stats optimization
_USE_STATS = True


def pick_best_replacement(sentence, old, candidates):
    """从多个候选替换中挑选。

    原策略：选 perplexity 最高的（最不可预测）。实测发现会偏向最离谱的候选。
    新策略：按 ppl 升序排序，取「次高」（n>=3 时 index n-2，即非极端值）。

    Perf: we only need PERPLEXITY to rank candidates, NOT the full analyze_text
    (burstiness/entropy_cv/diveye/gltr are irrelevant for single-phrase ranking).
    Using compute_perplexity() directly drops 10k-char academic humanize time from
    ~30s to <5s (profiler showed analyze_text was 99% of hot path).
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
        # Only perplexity (no window_size → skip window perplexities). Faster than analyze_text.
        ppl_result = compute_perplexity(new_sentence, window_size=0)
        scored.append((candidate, ppl_result.get('perplexity', 0)))

    scored.sort(key=lambda x: x[1])  # ascending
    n = len(scored)
    if n <= 2:
        return scored[-1][0]
    return scored[n - 2][0]


def _compute_burstiness(text):
    """计算文本的 burstiness。"""
    if not _USE_STATS or not ngram_analyze:
        return None
    stats = ngram_analyze(text)
    return stats.get('burstiness', None)


# Import perplexity-boosting strategies from humanize_cn
try:
    from humanize_cn import (reduce_high_freq_bigrams, randomize_sentence_lengths,
                             inject_noise_expressions)
except ImportError:
    try:
        from scripts.humanize_cn import (reduce_high_freq_bigrams, randomize_sentence_lengths,
                                         inject_noise_expressions)
    except ImportError:
        reduce_high_freq_bigrams = None
        randomize_sentence_lengths = None
        inject_noise_expressions = None

# Module-level flag: whether to apply noise strategies
_USE_NOISE = True

HEDGING_INJECTIONS = [
    '在一定程度上', '从某种角度看', '初步来看', '大体上',
    '就目前而言', '在多数情况下', '就现有研究来看',
    '从目前的情况看', '在一定条件下', '大致可以认为',
]

# Author subjectivity expressions
AUTHOR_VOICE = [
    '笔者认为', '笔者以为', '本研究发现', '就笔者的观察',
    '从笔者的分析来看', '据笔者了解', '笔者倾向于',
    '在笔者看来', '笔者注意到',
]


def _replace_academic_phrases(text, aggressive=False):
    """Replace AI academic phrases with natural alternatives.
    
    Uses per-character sentinel interleaving to prevent cascade replacements
    where a replacement's text contains another pattern as substring.
    Uses pick_best_replacement for perplexity-optimized selection when stats enabled.
    """
    SENTINEL = '\x00'  # Null byte — won't appear in normal Chinese text
    sorted_phrases = sorted(ACADEMIC_REPLACEMENTS.keys(), key=len, reverse=True)

    for phrase in sorted_phrases:
        alternatives = ACADEMIC_REPLACEMENTS[phrase]
        if isinstance(alternatives, str):
            alternatives = [alternatives]

        while phrase in text:
            replacement = pick_best_replacement(text, phrase, alternatives)
            # Interleave sentinels between each character to prevent substring matching
            protected = SENTINEL.join(replacement)
            text = text.replace(phrase, protected, 1)

    # Strip all sentinels
    text = text.replace(SENTINEL, '')
    return text


def _inject_hedging(text, aggressive=False):
    """Add academic hedging language to overly certain statements.
    Processes paragraph by paragraph to preserve paragraph breaks."""
    paragraphs = text.split('\n\n')
    result_paragraphs = []
    injected = 0
    total_sents = len(split_sentences(text))
    max_inject = max(2, total_sents // 8) if not aggressive else max(3, total_sents // 5)

    for para in paragraphs:
        sentences = split_sentences(para)
        result = []

        for sent in sentences:
            has_certainty = any(m in sent for m in CERTAINTY_MARKERS)
            has_hedging = any(m in sent for m in HEDGING_MARKERS)

            if has_certainty and not has_hedging and injected < max_inject:
                still_certain = any(m in sent for m in CERTAINTY_MARKERS)
                if still_certain:
                    for cm in CERTAINTY_MARKERS:
                        if cm in sent:
                            hedge = random.choice(HEDGING_INJECTIONS)
                            sent = sent.replace(cm, hedge, 1)
                            injected += 1
                            break
            elif not has_hedging and random.random() < (0.08 if not aggressive else 0.15) and injected < max_inject:
                # Don't inject hedging right after structural words
                skip_starters = ['首先', '其次', '最后', '第一', '第二', '第三']
                starts_structural = any(sent.strip().startswith(s) for s in skip_starters)
                if '，' in sent and not starts_structural:
                    parts = sent.split('，', 1)
                    # Only inject if first part is substantial (>4 chars)
                    if count_chinese(parts[0]) > 4:
                        hedge = random.choice(HEDGING_INJECTIONS)
                        sent = parts[0] + '，' + hedge + '，' + parts[1]
                        injected += 1

            result.append(sent)

        result_paragraphs.append(''.join(result))

    return '\n\n'.join(result_paragraphs)


def _add_author_voice(text, aggressive=False):
    """Replace impersonal 'research shows' with author voice.
    Only replaces when the phrase appears at sentence-start positions
    (after period, newline, or at the very beginning)."""
    impersonal = ['研究表明', '研究发现', '研究显示', '研究指出', '分析表明']
    replaced = 0
    max_replace = 3 if not aggressive else 5

    for phrase in impersonal:
        # Only replace at natural sentence boundaries
        for prefix in ['。', '\n', '，']:
            target = prefix + phrase
            while target in text and replaced < max_replace:
                voice = random.choice(AUTHOR_VOICE)
                text = text.replace(target, prefix + voice, 1)
                replaced += 1
        # Also check sentence start
        if text.startswith(phrase) and replaced < max_replace:
            voice = random.choice(AUTHOR_VOICE)
            text = voice + text[len(phrase):]
            replaced += 1

    return text


def _break_uniform_structure(text):
    """Vary paragraph structure to break AI-like uniformity.
    Preserves paragraph breaks (\n\n)."""
    paragraphs = text.split('\n\n')
    if len(paragraphs) < 3:
        return text

    result = []
    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]
        if not para.strip():
            result.append(para)
            i += 1
            continue

        # Occasionally merge two short adjacent paragraphs
        if (i + 1 < len(paragraphs) and
                count_chinese(para) < 60 and
                count_chinese(paragraphs[i + 1]) < 60 and
                paragraphs[i + 1].strip() and
                random.random() < 0.25):
            merged = para.rstrip() + '\n' + paragraphs[i + 1].lstrip()
            result.append(merged)
            i += 2
            continue

        # Vary sentence structure within paragraph
        sentences = split_sentences(para)
        if len(sentences) >= 4:
            if random.random() < 0.15 and len(sentences) >= 3:
                mid = len(sentences) // 2
                sentences[mid], sentences[mid - 1] = sentences[mid - 1], sentences[mid]

        result.append(''.join(sentences))
        i += 1

    return '\n\n'.join(result)


def _reduce_connectors(text, aggressive=False):
    """Reduce density of logical connectors."""
    # Only remove some, not all — keep academic coherence
    removable = ['此外，', '另外，', '与此同时，', '不仅如此，', '事实上，', '实际上，']
    removed = 0
    max_remove = 3 if not aggressive else 6

    for conn in removable:
        while conn in text and removed < max_remove:
            if random.random() < 0.5:
                text = text.replace(conn, '', 1)
                removed += 1
            else:
                break

    return text


def _shorten_long_sentences(text, max_chars=90):
    """Split overly long academic sentences at natural breakpoints, with burstiness guard."""
    burst_before = _compute_burstiness(text)

    sentences = re.split(r'([。])', text)
    result = []

    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''

        if count_chinese(sent) > max_chars:
            # Find a split point
            split_words = ['但是', '不过', '然而', '同时', '而且', '因此', '所以', '并且']
            split_done = False
            for sw in split_words:
                pos = sent.find('，' + sw)
                if pos > 10 and pos < len(sent) - 10:
                    result.append(sent[:pos] + '。' + sent[pos + 1:] + punct)
                    split_done = True
                    break
            if not split_done:
                # Split at a comma near middle
                commas = [m.start() for m in re.finditer('，', sent)]
                if commas:
                    mid = len(sent) // 2
                    best = min(commas, key=lambda x: abs(x - mid))
                    if best > 10 and best < len(sent) - 10:
                        result.append(sent[:best] + '。' + sent[best + 1:] + punct)
                    else:
                        result.append(sent + punct)
                else:
                    result.append(sent + punct)
        else:
            result.append(sent + punct)

    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])

    new_text = ''.join(result)

    # Burstiness guard: if splitting made text more uniform, revert
    if burst_before is not None:
        burst_after = _compute_burstiness(new_text)
        if burst_after is not None and burst_after < burst_before * 0.8:
            return text

    return new_text


def _diversify_data_narration(text):
    """Make data narration less template-like."""
    # Already handled by ACADEMIC_REPLACEMENTS
    return text


def _add_limitation_markers(text, aggressive=False):
    """If conclusion section lacks limitations, add mild hedging."""
    tail_start = int(len(text) * 0.8)
    tail = text[tail_start:]

    has_limitation = any(m in tail for m in LIMITATION_MARKERS)
    if has_limitation:
        return text

    # Check if there are perfect conclusion phrases
    has_perfect = any(re.search(p, tail) for p in PERFECT_CONCLUSION_PHRASES)
    if not has_perfect:
        return text

    # Add a mild limitation note
    limitations = [
        '当然，本研究也存在一定的局限：',
        '需要指出的是，本研究仍有若干不足之处。',
        '受限于研究条件，本文的结论在推广性方面尚有不足。',
        '本研究的样本和方法存在一定的局限，后续研究可进一步完善。',
    ]
    addition = random.choice(limitations)

    # Insert before last sentence
    last_period = tail.rfind('。')
    if last_period > 0:
        new_tail = tail[:last_period + 1] + addition + tail[last_period + 1:]
        text = text[:tail_start] + new_tail

    return text


def humanize_academic(text, aggressive=False, seed=None):
    """Apply all academic humanization transforms."""
    if seed is not None:
        random.seed(seed)

    # 1. Replace AI academic phrases
    text = _replace_academic_phrases(text, aggressive)

    # 1b. Deep sentence restructuring (句级改写)
    try:
        from restructure_cn import deep_restructure
    except ImportError:
        try:
            from scripts.restructure_cn import deep_restructure
        except ImportError:
            deep_restructure = None
    if deep_restructure:
        text = deep_restructure(text, aggressive=aggressive, scene='academic')

    # 2. Reduce connector density
    text = _reduce_connectors(text, aggressive)

    # 3. Add author voice
    text = _add_author_voice(text, aggressive)

    # 4. Inject hedging language
    text = _inject_hedging(text, aggressive)

    # 5. Break uniform structure
    text = _break_uniform_structure(text)

    # 6. Shorten long sentences
    text = _shorten_long_sentences(text)

    # 7. Diversify data narration (via replacements)
    text = _diversify_data_narration(text)

    # 8. Add limitation markers if needed
    text = _add_limitation_markers(text, aggressive)

    # ── NEW: Three perplexity-boosting strategies ──

    # Strategy 1: Low-frequency bigram injection (always active)
    # scene='academic' filters ACADEMIC_PRESERVE_WORDS (研究/系统/应用 etc.) and
    # ACADEMIC_BLACKLIST_CANDIDATES (施用/本事/拉高 etc.) to keep the output readable
    # as an academic paper.
    if reduce_high_freq_bigrams:
        bigram_strength = 0.5 if aggressive else 0.3
        text = reduce_high_freq_bigrams(text, strength=bigram_strength, scene='academic')
    
    # Strategy 2 & 3: Noise injection (skipped with --no-noise)
    if _USE_NOISE:
        # Strategy 3: Noise expression injection (academic style — restrained)
        if inject_noise_expressions:
            noise_density = 0.2 if aggressive else 0.1
            text = inject_noise_expressions(text, density=noise_density, style='academic')
        
        # Strategy 2: Sentence length randomization
        if randomize_sentence_lengths:
            text = randomize_sentence_lengths(text, aggressive=aggressive, seed=seed)

    # Clean up
    text = re.sub(r'[，,]{2,}', '，', text)
    text = re.sub(r'[。]{2,}', '。', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'，。', '。', text)
    text = re.sub(r'。，', '。', text)
    # Fix doubled characters from replacement artifacts
    text = re.sub(r'已已', '已', text)
    text = re.sub(r'会会', '会', text)
    text = re.sub(r'了了', '了', text)
    text = re.sub(r'的的', '的', text)
    text = re.sub(r'是是', '是', text)
    text = re.sub(r'在在', '在', text)
    # Fix phrase-level duplications (e.g. "为后续研究为后续研究")
    text = re.sub(r'([\u4e00-\u9fff]{4,12})\1', r'\1', text)

    # ── Final verification loop (stats-optimized) ──
    # Run per-paragraph so \n\n survives. The previous implementation used
    # split_sentences which splits on [。！？\n] and the following ''.join() ate all
    # paragraph breaks, collapsing the 5-paragraph input into one blob.
    if _USE_STATS and ngram_analyze:
        stats = ngram_analyze(text)
        ppl = stats.get('perplexity', 0)
        if 0 < ppl < 200 and count_chinese(text) >= 100:
            sorted_phrases = sorted(ACADEMIC_REPLACEMENTS.keys(), key=len, reverse=True)

            def _fix_paragraph(para, rng_seed):
                # Split on sentence punctuation only, keeping delimiters.
                parts = re.split(r'([。！？])', para)
                sentences = []
                for i in range(0, len(parts) - 1, 2):
                    s = parts[i]
                    p = parts[i + 1] if i + 1 < len(parts) else ''
                    if s.strip():
                        sentences.append(s + p)
                if len(parts) % 2 == 1 and parts[-1].strip():
                    sentences.append(parts[-1])

                sent_scores = []
                for i, s in enumerate(sentences):
                    if count_chinese(s) < 5:
                        continue
                    s_stats = ngram_analyze(s)
                    sent_scores.append((i, s_stats.get('perplexity', 0)))

                if not sent_scores:
                    return para

                sent_scores.sort(key=lambda x: x[1])
                n_fix = min(3, max(1, len(sent_scores) // 5))

                if rng_seed is not None:
                    random.seed(rng_seed)

                for idx, _ in sent_scores[:n_fix]:
                    sent = sentences[idx]
                    for phrase in sorted_phrases:
                        if phrase in sent:
                            alternatives = ACADEMIC_REPLACEMENTS[phrase]
                            if isinstance(alternatives, str):
                                alternatives = [alternatives]
                            best = pick_best_replacement(sent, phrase, alternatives)
                            sentences[idx] = sent.replace(phrase, best, 1)
                            break
                return ''.join(sentences)

            paragraphs = text.split('\n\n')
            seed_base = seed + 1 if seed is not None else None
            fixed = [
                _fix_paragraph(p, seed_base + i if seed_base is not None else None)
                for i, p in enumerate(paragraphs)
            ]
            text = '\n\n'.join(fixed)

    return text.strip()


# ═══════════════════════════════════════════════════════════════════
#  Output Formatting
# ═══════════════════════════════════════════════════════════════════

DIMENSION_NAMES = {
    'ai_academic_phrases':   ('🔴', 'AI 学术措辞'),
    'passive_overuse':       ('🟠', '被动句式过度'),
    'paragraph_uniformity':  ('🟠', '段落结构整齐'),
    'connector_density':     ('🟠', '逻辑连接词密集'),
    'synonym_poverty':       ('🟡', '同义表达匮乏'),
    'citation_integration':  ('🟡', '引用整合度低'),
    'data_template':         ('🟡', '数据论述模板化'),
    'over_enumeration':      ('🟡', '过度列举'),
    'perfect_conclusion':    ('🟠', '结论过于圆满'),
    'certainty_overuse':     ('🟠', '语气过于确定'),
    'low_topic_diffusion':   ('🟠', '扩散度低（主题重叠）'),
    # Statistical features
    'stat_low_perplexity':   ('📊', '困惑度异常低'),
    'stat_low_burstiness':   ('📊', '困惑度变化均匀'),
    'stat_uniform_entropy':  ('📊', '段落熵值均匀'),
}


def format_detect_output(issues, metrics, score, as_json=False, score_only=False, verbose=False):
    level = score_to_level(score)
    total_issues = sum(len(v) for v in issues.values())

    if score_only:
        return f'{score}/100 ({level})'

    if as_json:
        result = {
            'score': score,
            'level': level,
            'metrics': metrics,
            'total_issues': total_issues,
            'issues': {},
        }
        for cat, items in issues.items():
            result['issues'][cat] = [
                {'text': it['text'], 'count': it.get('count', 1), 'severity': it['severity']}
                for it in items
            ]
        return json.dumps(result, ensure_ascii=False, indent=2)

    lines = []
    bar_len = 20
    filled = int(score / 100 * bar_len)
    bar = '█' * filled + '░' * (bar_len - filled)
    lines.append(f'学术 AIGC 评分: {score}/100 [{bar}] {level.upper().replace("_", " ")}')
    lines.append(f'字符: {metrics["char_count"]} | 句子: {metrics["sentence_count"]} | 段落: {metrics["paragraph_count"]}')
    if metrics.get('entropy'):
        lines.append(f'信息熵: {metrics["entropy"]:.2f} | 连接词密度: {metrics["connector_density"]:.1f}/百字')
    lines.append(f'确定性表述: {metrics["certainty_count"]} | 学术留白: {metrics["hedging_count"]} | 引用: {metrics["citation_count"]}')
    if metrics.get('perplexity'):
        lines.append(f'困惑度: {metrics["perplexity"]:.1f} | 突发度: {metrics.get("burstiness", 0):.3f} | 段落熵CV: {metrics.get("entropy_cv", 0):.3f}')
    lines.append(f'问题总数: {total_issues}')
    lines.append('')

    dim_order = [
        'ai_academic_phrases', 'passive_overuse', 'paragraph_uniformity',
        'connector_density', 'synonym_poverty', 'citation_integration',
        'data_template', 'over_enumeration', 'perfect_conclusion', 'certainty_overuse',
        'low_topic_diffusion',
        'stat_low_perplexity', 'stat_low_burstiness', 'stat_uniform_entropy',
    ]
    for dim in dim_order:
        if dim not in issues or not issues[dim]:
            continue
        icon, name = DIMENSION_NAMES.get(dim, ('⚪', dim))
        items = issues[dim]
        # Count non-info items
        real_items = [it for it in items if it.get('severity') != 'info']
        lines.append(f'{icon} {name} ({len(real_items)})')
        show_count = 8 if verbose else 4
        for item in items[:show_count]:
            sev = item.get('severity', 'medium')
            if sev == 'info':
                lines.append(f'   {item["text"]}')
            else:
                count_str = f' ×{item["count"]}' if item.get('count', 1) > 1 else ''
                lines.append(f'   {item["text"]}{count_str}')
        if len(items) > show_count:
            lines.append(f'   ... 还有 {len(items) - show_count} 项')
        lines.append('')

    return '\n'.join(lines)


def format_comparison(before_issues, before_metrics, before_score,
                      after_issues, after_metrics, after_score,
                      before_general=None, after_general=None):
    """Format before/after comparison.

    before_general / after_general: tuple (score, level) from detect_cn, or None.
    When both are provided, the general score is displayed alongside the academic one —
    this matters because users optimizing for CNKI/VIP-style detectors care about the
    general score, not the academic-specific weighted one (which uses a 0.7 multiplier).
    """
    lines = []
    b_level = score_to_level(before_score)
    a_level = score_to_level(after_score)

    b_bar = '█' * int(before_score / 100 * 20) + '░' * (20 - int(before_score / 100 * 20))
    a_bar = '█' * int(after_score / 100 * 20) + '░' * (20 - int(after_score / 100 * 20))

    lines.append('═══ 学术 AIGC 对比结果 ═══\n')
    lines.append('学术专用评分 (10 维度，含 ×0.7 权重):')
    lines.append(f'  原文:   {before_score:3d}/100 [{b_bar}] {b_level.upper().replace("_"," ")}')
    lines.append(f'  改写后: {after_score:3d}/100 [{a_bar}] {a_level.upper().replace("_"," ")}')

    diff = before_score - after_score
    if diff > 0:
        lines.append(f'  ✅ 降低了 {diff} 分')
    elif diff == 0:
        lines.append(f'  ⚠️  分数未变化')
    else:
        lines.append(f'  ❌ 分数上升了 {abs(diff)} 分')

    # General AIGC score (same scoring function as detect_cn.py)
    if before_general is not None and after_general is not None:
        g_before, g_before_lvl = before_general
        g_after, g_after_lvl = after_general
        g_b_bar = '█' * int(g_before / 100 * 20) + '░' * (20 - int(g_before / 100 * 20))
        g_a_bar = '█' * int(g_after / 100 * 20) + '░' * (20 - int(g_after / 100 * 20))
        lines.append('')
        lines.append('通用 AIGC 评分 (同 detect_cn.py，更接近 CNKI/VIP 风格检测器):')
        lines.append(f'  原文:   {g_before:3d}/100 [{g_b_bar}] {g_before_lvl.upper().replace("_"," ")}')
        lines.append(f'  改写后: {g_after:3d}/100 [{g_a_bar}] {g_after_lvl.upper().replace("_"," ")}')
        g_diff = g_before - g_after
        if g_diff > 0:
            lines.append(f'  ✅ 降低了 {g_diff} 分')
        elif g_diff == 0:
            lines.append(f'  ⚠️  分数未变化')
        else:
            lines.append(f'  ❌ 分数上升了 {abs(g_diff)} 分')

    # Dimension breakdown
    all_dims = set(list(before_issues.keys()) + list(after_issues.keys()))
    if all_dims:
        lines.append('\n── 各维度变化 ──')
        for dim in ['ai_academic_phrases', 'passive_overuse', 'paragraph_uniformity',
                     'connector_density', 'synonym_poverty', 'citation_integration',
                     'data_template', 'over_enumeration', 'perfect_conclusion', 'certainty_overuse']:
            if dim not in all_dims:
                continue
            b_count = len([i for i in before_issues.get(dim, []) if i.get('severity') != 'info'])
            a_count = len([i for i in after_issues.get(dim, []) if i.get('severity') != 'info'])
            if b_count == 0 and a_count == 0:
                continue
            _, name = DIMENSION_NAMES.get(dim, ('', dim))
            status = '✅' if a_count < b_count else ('➖' if a_count == b_count else '❌')
            lines.append(f'  {status} {name}: {b_count} → {a_count}')

    # Key metrics
    lines.append('\n── 关键指标 ──')
    lines.append(f'  确定性表述: {before_metrics["certainty_count"]} → {after_metrics["certainty_count"]}')
    lines.append(f'  学术留白:   {before_metrics["hedging_count"]} → {after_metrics["hedging_count"]}')
    lines.append(f'  连接词密度: {before_metrics["connector_density"]:.1f} → {after_metrics["connector_density"]:.1f}/百字')

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='中文学术论文 AIGC 检测与改写工具 v1.0 — 针对知网/维普检测标准优化',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''示例:
  python academic_cn.py paper.txt                    # 检测 + 改写
  python academic_cn.py paper.txt --detect-only      # 仅检测
  python academic_cn.py paper.txt -o clean.txt       # 改写并保存
  python academic_cn.py paper.txt -o clean.txt -a    # 激进模式
  python academic_cn.py paper.txt -o clean.txt --compare  # 对比模式
''')
    parser.add_argument('file', nargs='?', help='输入文件路径（不指定则从 stdin 读取）')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--detect-only', action='store_true', help='仅检测，不改写')
    parser.add_argument('-a', '--aggressive', action='store_true', help='激进模式（改写更多）')
    parser.add_argument('--compare', action='store_true', help='对比模式（显示改写前后评分变化）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 输出')
    parser.add_argument('-s', '--score', action='store_true', help='仅输出分数')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细模式')
    parser.add_argument('--seed', type=int, help='随机种子（可复现）')
    parser.add_argument('--no-stats', action='store_true',
                       help='跳过统计优化（困惑度反馈），回退到纯规则替换')
    parser.add_argument('--no-noise', action='store_true',
                       help='跳过噪声策略（句长随机化 + 噪声表达插入）')
    parser.add_argument('--quick', action='store_true',
                       help='快速模式（= --no-stats --no-noise），只跑短语替换 + 结构清理，'
                            '长文本 <1s，适合先粗过一遍看大概效果')

    args = parser.parse_args()

    # Toggle stats optimization
    global _USE_STATS
    _USE_STATS = not (args.no_stats or args.quick)

    # Toggle noise strategies
    global _USE_NOISE
    _USE_NOISE = not (args.no_noise or args.quick)

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

    # Detect
    issues, metrics = detect_academic(text)
    score = calculate_academic_score(issues)

    if args.detect_only or (not args.output and not args.compare):
        # Detection only mode
        output = format_detect_output(issues, metrics, score,
                                      as_json=args.json, score_only=args.score, verbose=args.verbose)
        print(output)
        return

    # Humanize
    humanized = humanize_academic(text, aggressive=args.aggressive, seed=args.seed)

    if args.compare:
        # Run both academic and general detection on humanized text
        after_issues, after_metrics = detect_academic(humanized)
        after_score = calculate_academic_score(after_issues)
        # General AIGC scores (same scoring as detect_cn.py, more predictive of CNKI/VIP)
        before_general = after_general = None
        g_before, _, _ = _compute_general_score(text)
        g_after, _, _ = _compute_general_score(humanized)
        if g_before is not None and g_after is not None:
            before_general = (g_before, score_to_level(g_before))
            after_general = (g_after, score_to_level(g_after))
        print(format_comparison(issues, metrics, score, after_issues, after_metrics, after_score,
                                before_general=before_general, after_general=after_general))

    # Save output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(humanized)
        mode = ' (激进模式)' if args.aggressive else ''
        print(f'✓ 已保存到 {args.output}{mode}')

        if not args.compare:
            # Quick score comparison — report academic + general scores side by side
            after_issues, after_metrics = detect_academic(humanized)
            after_score = calculate_academic_score(after_issues)
            diff = score - after_score
            print(f'  学术专用: {score}/100 → {after_score}/100', end='')
            if diff > 0:
                print(f'  (降 {diff})')
            else:
                print()
            g_before, _, _ = _compute_general_score(text)
            g_after, _, _ = _compute_general_score(humanized)
            if g_before is not None and g_after is not None:
                g_diff = g_before - g_after
                print(f'  通用评分: {g_before}/100 → {g_after}/100', end='')
                if g_diff > 0:
                    print(f'  (降 {g_diff})')
                else:
                    print()
    else:
        # No output file, no compare — print humanized text
        print(humanized)


if __name__ == '__main__':
    main()
