#!/usr/bin/env python3
"""
Chinese AI Text Detector v2.0
Scans for AI-generated patterns in Chinese text
Features: 20+ detection categories, weighted 0-100 scoring, sentence-level analysis
"""

import sys
import json
import re
import os
import argparse
from collections import defaultdict
from math import log2

# Load patterns from JSON config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERNS_FILE = os.path.join(SCRIPT_DIR, 'patterns_cn.json')

def load_patterns():
    """Load patterns from external config, fall back to built-in"""
    if os.path.exists(PATTERNS_FILE):
        with open(PATTERNS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

CONFIG = load_patterns()

# ─── Detection Patterns ───

CRITICAL_PHRASES = {
    'mechanical_connectors': CONFIG['critical_patterns']['mechanical_connectors']['phrases'] if CONFIG else [
        '值得注意的是', '综上所述', '不难发现', '总而言之',
        '与此同时', '在此基础上', '由此可见', '不仅如此',
        '换句话说', '更重要的是', '需要强调的是', '不可否认',
        '显而易见', '不言而喻', '正如我们所知', '归根结底',
    ],
    'empty_grand_words': CONFIG['critical_patterns']['empty_grand_words']['phrases'] if CONFIG else [
        '赋能', '闭环', '智慧时代', '数字化转型', '生态',
        '愿景', '顶层设计', '协同增效', '降本增效', '打通壁垒',
        '深度融合', '创新驱动', '全方位', '多维度', '系统性',
    ],
}

CRITICAL_REGEX = CONFIG['critical_patterns']['three_part_structure']['regex'] if CONFIG else [
    r'首先[，,].*?其次[，,].*?最后',
    r'一方面[，,].*?另一方面',
    r'第一[，,].*?第二[，,].*?第三',
    r'其一[，,].*?其二[，,].*?其三',
]

HIGH_SIGNAL_PHRASES = {
    'ai_high_freq_words': CONFIG['high_signal_patterns']['ai_high_freq_words']['phrases'] if CONFIG else [
        '助力', '彰显', '凸显', '焕发', '深度剖析',
        '加持', '赛道', '破圈', '出圈', '颠覆', '革新',
        '底层逻辑', '抓手', '链路', '触达', '心智',
        '沉淀', '对齐', '拉通', '复盘', '迭代',
    ],
    'filler_phrases': CONFIG['high_signal_patterns']['filler_phrases']['phrases'] if CONFIG else [
        '值得一提的是', '需要指出的是', '不得不说',
        '毫无疑问', '众所周知', '正因如此',
        '具体来说', '简而言之', '换言之',
    ],
}

HIGH_SIGNAL_REGEX = {
    'balanced_arguments': CONFIG['high_signal_patterns']['balanced_arguments']['regex'] if CONFIG else [
        r'虽然.*?但是.*?同时',
        r'一方面.*?另一方面.*?总的来说',
    ],
    'template_sentences': CONFIG['high_signal_patterns']['template_sentences']['regex'] if CONFIG else [
        r'随着.*?的(不断)?发展',
        r'在.*?的背景下',
        r'在当今.*?时代',
        r'作为.*?的重要(组成部分|环节|手段)',
        r'对于.*?而言[，,].*?至关重要',
        r'这不仅.*?更是',
        r'从.*?角度(来看|来说|而言)',
        r'无论是.*?还是.*?都',
        r'可以说[，,]',
        r'总的来说[，,]',
    ],
}

HEDGING_PHRASES = CONFIG['medium_signal_patterns']['hedging_language']['phrases'] if CONFIG else [
    '在一定程度上', '或许', '某种程度上', '相对而言',
    '总体来说', '一般来说', '通常情况下',
]

EMOTIONAL_WORDS = CONFIG['style_signals']['emotional_words'] if CONFIG else [
    '愤怒', '高兴', '难过', '失望', '惊讶', '担心',
    '开心', '郁闷', '焦虑', '兴奋', '害怕', '感动',
    '烦躁', '痛苦', '崩溃', '无奈', '委屈', '舒服',
]

PERSONAL_MARKERS = CONFIG['style_signals']['personal_markers'] if CONFIG else [
    '我觉得', '我认为', '我个人', '在我看来', '说实话',
    '坦白讲', '老实说', '不瞒你说',
]

# ─── Utility ───

def count_chinese_chars(text):
    return len(re.findall(r'[\u4e00-\u9fff]', text))

def split_sentences(text):
    """Split text into sentences, handling Chinese punctuation"""
    parts = re.split(r'([。！？\n])', text)
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        if s:
            sentences.append(s + (parts[i+1] if i+1 < len(parts) else ''))
    # Handle last part if odd
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append(parts[-1].strip())
    return [s for s in sentences if len(s) > 1]

def char_entropy(text):
    """Calculate character-level entropy (proxy for perplexity)"""
    chars = re.findall(r'[\u4e00-\u9fff]', text)
    if len(chars) < 10:
        return 5.0  # Default
    
    # Bigram entropy
    bigrams = defaultdict(int)
    for i in range(len(chars) - 1):
        bigrams[chars[i] + chars[i+1]] += 1
    
    total = sum(bigrams.values())
    if total == 0:
        return 5.0
    
    entropy = 0
    for count in bigrams.values():
        p = count / total
        if p > 0:
            entropy -= p * log2(p)
    
    return entropy

# ─── Detection Engine ───

def detect_patterns(text):
    """Detect AI patterns in Chinese text. Returns (issues, metrics)"""
    issues = defaultdict(list)
    char_count = count_chinese_chars(text)
    sentences = split_sentences(text)
    
    # ── Critical: Three-part structure ──
    for pattern in CRITICAL_REGEX:
        for match in re.finditer(pattern, text, re.DOTALL):
            issues['three_part_structure'].append({
                'text': match.group()[:60],
                'severity': 'critical',
            })
    
    # ── Critical: Mechanical connectors ──
    for phrase in CRITICAL_PHRASES['mechanical_connectors']:
        count = text.count(phrase)
        if count > 0:
            issues['mechanical_connectors'].append({
                'text': phrase,
                'count': count,
                'severity': 'critical',
            })
    
    # ── Critical: Empty grand words ──
    for word in CRITICAL_PHRASES['empty_grand_words']:
        count = text.count(word)
        if count > 0:
            issues['empty_grand_words'].append({
                'text': word,
                'count': count,
                'severity': 'critical',
            })
    
    # ── High: AI high-frequency words ──
    for word in HIGH_SIGNAL_PHRASES['ai_high_freq_words']:
        count = text.count(word)
        if count > 0:
            issues['ai_high_freq_words'].append({
                'text': word,
                'count': count,
                'severity': 'high',
            })
    
    # ── High: Filler phrases ──
    for phrase in HIGH_SIGNAL_PHRASES['filler_phrases']:
        count = text.count(phrase)
        if count > 0:
            issues['filler_phrases'].append({
                'text': phrase,
                'count': count,
                'severity': 'high',
            })
    
    # ── High: Balanced arguments (AI loves both-sides) ──
    for pattern in HIGH_SIGNAL_REGEX.get('balanced_arguments', []):
        for match in re.finditer(pattern, text, re.DOTALL):
            issues['balanced_arguments'].append({
                'text': match.group()[:80],
                'severity': 'high',
            })
    
    # ── High: Template sentences ──
    for pattern in HIGH_SIGNAL_REGEX.get('template_sentences', []):
        for match in re.finditer(pattern, text):
            issues['template_sentences'].append({
                'text': match.group()[:60],
                'severity': 'high',
            })
    
    # ── Medium: Hedging/over-cautious language ──
    hedge_count = 0
    for phrase in HEDGING_PHRASES:
        c = text.count(phrase)
        if c > 0:
            hedge_count += c
    threshold = CONFIG['medium_signal_patterns']['hedging_language'].get('threshold', 5) if CONFIG else 5
    if hedge_count >= threshold:
        issues['hedging_language'].append({
            'text': f'谨慎用语 {hedge_count} 次（阈值 {threshold}）',
            'count': hedge_count,
            'severity': 'medium',
        })
    
    # ── Medium: List addiction ──
    list_patterns = [
        r'(?:(?:①|②|③|④|⑤).*?\n){3,}',
        r'(?:(?:\d\.)\s.*?\n){3,}',
        r'(?:(?:[-•·])\s.*?\n){4,}',
    ]
    for pattern in list_patterns:
        for match in re.finditer(pattern, text):
            issues['list_addiction'].append({
                'text': '列举过多',
                'severity': 'medium',
            })
    
    # ── Medium: Punctuation overuse ──
    if char_count > 0:
        em_dash_count = text.count('—')
        semicolon_count = text.count('；')
        
        if em_dash_count / char_count * 100 > 1.0:
            issues['punctuation_overuse'].append({
                'text': f'破折号 {em_dash_count} 个',
                'severity': 'medium',
            })
        if semicolon_count / char_count * 100 > 0.5:
            issues['punctuation_overuse'].append({
                'text': f'分号 {semicolon_count} 个',
                'severity': 'medium',
            })
    
    # ── Medium: Parallel structures (excessive rhetoric) ──
    parallel_pattern = r'[，,][^，,。！？]{4,10}[；;，,][^，,。！？]{4,10}[。！？]'
    parallels = re.findall(parallel_pattern, text)
    if len(parallels) > 2:
        issues['excessive_rhetoric'].append({
            'text': f'对偶/排比 {len(parallels)} 处',
            'severity': 'medium',
        })
    
    # ── Style: Uniform paragraph lengths ──
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip() and len(p.strip()) > 20]
    if len(paragraphs) >= 3:
        lengths = [len(p) for p in paragraphs]
        avg_len = sum(lengths) / len(lengths)
        if avg_len > 0:
            cv = (sum((l - avg_len) ** 2 for l in lengths) / len(lengths)) ** 0.5 / avg_len
            if cv < 0.2:  # Coefficient of variation < 20%
                issues['uniform_paragraphs'].append({
                    'text': f'段落长度 CV={cv:.2f}，过于均匀',
                    'severity': 'style',
                })
    
    # ── Style: Low burstiness (sentence length uniformity) ──
    if len(sentences) > 5:
        sent_lens = [count_chinese_chars(s) for s in sentences]
        avg_sl = sum(sent_lens) / len(sent_lens)
        if avg_sl > 0:
            cv_sent = (sum((l - avg_sl) ** 2 for l in sent_lens) / len(sent_lens)) ** 0.5 / avg_sl
            if cv_sent < 0.25:
                issues['low_burstiness'].append({
                    'text': f'句子长度 CV={cv_sent:.2f}，缺少节奏变化',
                    'severity': 'style',
                })
    
    # ── Style: Emotional flatness ──
    emotional_count = sum(text.count(w) for w in EMOTIONAL_WORDS)
    personal_count = sum(text.count(w) for w in PERSONAL_MARKERS)
    if char_count > 300:
        emotional_density = (emotional_count + personal_count) / char_count * 100
        if emotional_density < 0.15:
            issues['emotional_flatness'].append({
                'text': f'情感/个人表达密度 {emotional_density:.2f}%，偏低',
                'severity': 'style',
            })
    
    # ── Style: Repetitive sentence starters ──
    if len(sentences) > 5:
        starters = defaultdict(int)
        for s in sentences:
            s = s.strip()
            if len(s) >= 2:
                starters[s[:2]] += 1
        max_repeat = max(starters.values()) if starters else 0
        if max_repeat >= 3:
            top_starter = max(starters, key=starters.get)
            issues['repetitive_starters'].append({
                'text': f'"{top_starter}..." 出现 {max_repeat} 次',
                'severity': 'style',
            })
    
    # ── Style: Low entropy (predictable) ──
    entropy = char_entropy(text)
    if entropy < 6.0 and char_count > 200:
        issues['low_entropy'].append({
            'text': f'字符熵 {entropy:.2f}（越低越可预测）',
            'severity': 'style',
        })
    
    # ── Compute metrics ──
    metrics = {
        'char_count': char_count,
        'sentence_count': len(sentences),
        'paragraph_count': len(paragraphs),
        'entropy': entropy if char_count > 200 else None,
        'emotional_density': (emotional_count + personal_count) / char_count * 100 if char_count > 0 else 0,
    }
    
    return issues, metrics

# ─── Scoring ───

SEVERITY_WEIGHTS = {
    'critical': 8,
    'high': 4,
    'medium': 2,
    'style': 1.5,
}

def calculate_score(issues, metrics):
    """
    Calculate AI probability score (0-100).
    Higher = more likely AI-generated.
    """
    raw = 0
    
    for category, items in issues.items():
        for item in items:
            severity = item.get('severity', 'medium')
            weight = SEVERITY_WEIGHTS.get(severity, 2)
            count = item.get('count', 1)
            # Diminishing returns for repeated items
            raw += weight * min(count, 5)
    
    # Normalize: cap at 100
    # Typical AI text scores 40-80 raw, human text 0-15
    score = min(100, int(raw * 1.2))
    
    # Bonus penalties
    if metrics.get('emotional_density', 1) < 0.1 and metrics['char_count'] > 500:
        score = min(100, score + 5)
    
    if metrics.get('entropy') and metrics['entropy'] < 5.5:
        score = min(100, score + 5)
    
    return score

def score_to_level(score):
    """Convert numeric score to level"""
    if score >= 75:
        return 'very_high'
    elif score >= 50:
        return 'high'
    elif score >= 25:
        return 'medium'
    else:
        return 'low'

# ─── Sentence-level Analysis ───

def analyze_sentences(text, top_n=5):
    """Find the most AI-like sentences"""
    sentences = split_sentences(text)
    scored = []
    
    all_bad_phrases = (
        CRITICAL_PHRASES['mechanical_connectors'] +
        CRITICAL_PHRASES['empty_grand_words'] +
        HIGH_SIGNAL_PHRASES['ai_high_freq_words'] +
        HIGH_SIGNAL_PHRASES['filler_phrases']
    )
    
    all_bad_regex = CRITICAL_REGEX + HIGH_SIGNAL_REGEX.get('template_sentences', [])
    
    for sent in sentences:
        s = 0
        reasons = []
        
        # Check phrases
        for phrase in all_bad_phrases:
            if phrase in sent:
                s += 3
                reasons.append(phrase)
        
        # Check regex
        for pattern in all_bad_regex:
            if re.search(pattern, sent):
                s += 5
                reasons.append(f'模板: {pattern[:20]}')
        
        if s > 0:
            scored.append({
                'sentence': sent[:80],
                'score': s,
                'reasons': reasons[:3],
            })
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:top_n]

# ─── Output Formatting ───

CATEGORY_NAMES = {
    'three_part_structure': ('🔴', '三段式套路'),
    'mechanical_connectors': ('🔴', '机械连接词'),
    'empty_grand_words': ('🔴', '空洞宏大词'),
    'ai_high_freq_words': ('🟠', 'AI 高频词'),
    'filler_phrases': ('🟠', '套话/废话'),
    'balanced_arguments': ('🟠', '过度两面论'),
    'template_sentences': ('🟠', '模板句式'),
    'hedging_language': ('🟡', '过度谨慎'),
    'list_addiction': ('🟡', '列举上瘾'),
    'punctuation_overuse': ('🟡', '标点过度'),
    'excessive_rhetoric': ('🟡', '修辞过多'),
    'uniform_paragraphs': ('⚪', '段落均匀'),
    'low_burstiness': ('⚪', '节奏单一'),
    'emotional_flatness': ('⚪', '情感平淡'),
    'repetitive_starters': ('⚪', '句首重复'),
    'low_entropy': ('⚪', '低信息熵'),
}

def format_output(issues, metrics, score, sentences=None, as_json=False, score_only=False, verbose=False):
    total_issues = sum(len(v) for v in issues.values())
    level = score_to_level(score)
    
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
        if sentences:
            result['worst_sentences'] = sentences
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    # Human-readable
    lines = []
    
    # Score bar
    bar_len = 20
    filled = int(score / 100 * bar_len)
    bar = '█' * filled + '░' * (bar_len - filled)
    lines.append(f'AI 评分: {score}/100 [{bar}] {level.upper().replace("_", " ")}')
    lines.append(f'字符: {metrics["char_count"]} | 句子: {metrics["sentence_count"]} | 段落: {metrics["paragraph_count"]}')
    if metrics.get('entropy'):
        lines.append(f'信息熵: {metrics["entropy"]:.2f} | 情感密度: {metrics["emotional_density"]:.2f}%')
    lines.append(f'问题总数: {total_issues}')
    lines.append('')
    
    # Issues by severity
    for cat in ['three_part_structure', 'mechanical_connectors', 'empty_grand_words',
                'ai_high_freq_words', 'filler_phrases', 'balanced_arguments', 'template_sentences',
                'hedging_language', 'list_addiction', 'punctuation_overuse', 'excessive_rhetoric',
                'uniform_paragraphs', 'low_burstiness', 'emotional_flatness', 'repetitive_starters', 'low_entropy']:
        if cat not in issues or not issues[cat]:
            continue
        icon, name = CATEGORY_NAMES.get(cat, ('⚪', cat))
        items = issues[cat]
        lines.append(f'{icon} {name} ({len(items)})')
        show_count = 5 if verbose else 3
        for item in items[:show_count]:
            count_str = f' ×{item["count"]}' if item.get('count', 1) > 1 else ''
            lines.append(f'   {item["text"]}{count_str}')
        if len(items) > show_count:
            lines.append(f'   ... 还有 {len(items) - show_count} 个')
        lines.append('')
    
    # Worst sentences
    if sentences and verbose:
        lines.append('── 最可疑句子 ──')
        for i, s in enumerate(sentences, 1):
            lines.append(f'  {i}. [{s["score"]}分] {s["sentence"]}')
            lines.append(f'     原因: {", ".join(s["reasons"])}')
        lines.append('')
    
    return '\n'.join(lines)

# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description='中文 AI 文本检测 v2.0')
    parser.add_argument('file', nargs='?', help='输入文件路径（不指定则从 stdin 读取）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 输出')
    parser.add_argument('-s', '--score', action='store_true', help='仅输出分数')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细模式（含逐句分析）')
    parser.add_argument('--sentences', type=int, default=5, help='显示最可疑的 N 个句子')
    
    args = parser.parse_args()
    
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
    issues, metrics = detect_patterns(text)
    score = calculate_score(issues, metrics)
    
    # Sentence analysis (verbose mode)
    worst_sentences = None
    if args.verbose or args.json:
        worst_sentences = analyze_sentences(text, args.sentences)
    
    # Output
    output = format_output(issues, metrics, score, worst_sentences,
                          as_json=args.json, score_only=args.score, verbose=args.verbose)
    print(output)

if __name__ == '__main__':
    main()
