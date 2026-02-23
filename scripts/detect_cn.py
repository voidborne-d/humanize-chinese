#!/usr/bin/env python3
"""
Chinese AI Text Detector
Scans for AI-generated patterns in Chinese text
"""

import sys
import json
import re
from collections import defaultdict

# Detection patterns
PATTERNS = {
    # Critical patterns
    'three_part_structure': [
        r'首先[，,].*其次[，,].*最后',
        r'一方面[，,].*另一方面',
        r'第一[，,].*第二[，,].*第三',
    ],
    'mechanical_connectors': [
        '值得注意的是', '综上所述', '不难发现', '总而言之',
        '与此同时', '在此基础上', '由此可见', '此外',
    ],
    'empty_grand_words': [
        '赋能', '闭环', '智慧时代', '数字化转型', '生态',
        '愿景', '力量', '成就', '未来展望',
    ],
    
    # High signal patterns
    'ai_high_freq_words': [
        '助力', '彰显', '凸显', '焕发', '深度剖析',
        '解构', '量子纠缠', '光谱', '加持',
    ],
    'technical_jargon': [
        '解构', '量子纠缠', '赛博', '光谱', '维度',
    ],
    
    # Medium signal patterns
    'filler_phrases': [
        '值得一提的是', '需要指出的是', '不得不说',
        '毫无疑问', '显而易见', '众所周知',
    ],
    
    # Punctuation patterns
    'em_dash': '—',
    'semicolon': '；',
    'colon': '：',
}

# Replacements for humanization
REPLACEMENTS = {
    '值得注意的是': ['注意', '要提醒的是', '特别说一下'],
    '综上所述': ['总之', '说到底', '简单讲'],
    '不难发现': ['可以看到', '很明显'],
    '总而言之': ['总之', '总的来说'],
    '赋能': ['帮助', '提升', '支持'],
    '闭环': ['完整流程', '全链路'],
    '深度剖析': ['深入分析', '仔细看看'],
    '此外': ['另外', '还有'],
    '与此同时': ['同时', '这时候'],
}

def count_chinese_chars(text):
    """Count Chinese characters"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))

def detect_patterns(text):
    """Detect AI patterns in Chinese text"""
    issues = defaultdict(list)
    char_count = count_chinese_chars(text)
    
    # Critical: Three-part structure
    for pattern in PATTERNS['three_part_structure']:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            issues['three_part_structure'].append(match[:50])
    
    # Critical: Mechanical connectors
    for phrase in PATTERNS['mechanical_connectors']:
        count = text.count(phrase)
        if count > 0:
            issues['mechanical_connectors'].append(f'{phrase} ({count}x)')
    
    # Critical: Empty grand words
    for word in PATTERNS['empty_grand_words']:
        count = text.count(word)
        if count > 0:
            issues['empty_grand_words'].append(f'{word} ({count}x)')
    
    # High signal: AI high-frequency words
    for word in PATTERNS['ai_high_freq_words']:
        count = text.count(word)
        if count > 0:
            issues['ai_high_freq_words'].append(f'{word} ({count}x)')
    
    # High signal: Filler phrases
    for phrase in PATTERNS['filler_phrases']:
        count = text.count(phrase)
        if count > 0:
            issues['filler_phrases'].append(f'{phrase} ({count}x)')
    
    # Medium signal: Punctuation overuse
    em_dash_count = text.count(PATTERNS['em_dash'])
    semicolon_count = text.count(PATTERNS['semicolon'])
    colon_count = text.count(PATTERNS['colon'])
    
    if char_count > 0:
        em_dash_density = em_dash_count / char_count * 100
        semicolon_density = semicolon_count / char_count * 100
        
        if em_dash_density > 1.0:
            issues['punctuation_overuse'].append(f'破折号过多 ({em_dash_count})')
        if semicolon_density > 0.5:
            issues['punctuation_overuse'].append(f'分号过多 ({semicolon_count})')
    
    # Detect parallel structures (对偶句)
    parallel_pattern = r'[，,][^，,。！？]{4,10}[；;，,][^，,。！？]{4,10}[。！？]'
    parallels = re.findall(parallel_pattern, text)
    if len(parallels) > 2:
        issues['excessive_rhetoric'].append(f'对偶句过多 ({len(parallels)})')
    
    # Detect uniform paragraph lengths
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if len(paragraphs) >= 3:
        lengths = [len(p) for p in paragraphs]
        avg_len = sum(lengths) / len(lengths)
        variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
        if variance < avg_len * 0.1:  # Low variance = uniform
            issues['uniform_paragraphs'].append(f'段落长度过于均匀')
    
    return issues, char_count

def calculate_score(issues, char_count):
    """Calculate AI probability score"""
    total_issues = sum(len(v) for v in issues.values())
    
    # Critical patterns trigger very high
    critical_count = (
        len(issues.get('three_part_structure', [])) +
        len(issues.get('mechanical_connectors', [])) +
        len(issues.get('empty_grand_words', []))
    )
    
    if critical_count > 0:
        return 'very high'
    
    # Calculate density
    if char_count > 0:
        density = total_issues / char_count * 100
    else:
        density = 0
    
    if total_issues > 20 or density > 3:
        return 'high'
    elif total_issues > 10 or density > 1.5:
        return 'medium'
    else:
        return 'low'

def format_output(issues, char_count, score, as_json=False, score_only=False):
    """Format detection results"""
    total_issues = sum(len(v) for v in issues.values())
    
    if score_only:
        return score
    
    if as_json:
        return json.dumps({
            'score': score,
            'char_count': char_count,
            'total_issues': total_issues,
            'issues': dict(issues)
        }, ensure_ascii=False, indent=2)
    
    # Human-readable output
    lines = []
    lines.append(f'AI 概率: {score.upper()}')
    lines.append(f'字符数: {char_count}')
    lines.append(f'问题总数: {total_issues}')
    lines.append('')
    
    # Category breakdown
    category_names = {
        'three_part_structure': '【严重】三段式套路',
        'mechanical_connectors': '【严重】机械连接词',
        'empty_grand_words': '【严重】空洞宏大词',
        'ai_high_freq_words': '【高信号】AI 高频词',
        'filler_phrases': '【中等】套话',
        'excessive_rhetoric': '【高信号】过度修辞',
        'punctuation_overuse': '【中等】标点过度',
        'uniform_paragraphs': '【中等】段落均匀',
    }
    
    for category, name in category_names.items():
        if category in issues and issues[category]:
            lines.append(f'{name}: {len(issues[category])}')
            for item in issues[category][:3]:  # Show first 3
                lines.append(f'  - {item}')
            if len(issues[category]) > 3:
                lines.append(f'  ... 还有 {len(issues[category]) - 3} 个')
            lines.append('')
    
    return '\n'.join(lines)

def main():
    # Parse arguments
    as_json = '-j' in sys.argv
    score_only = '-s' in sys.argv
    
    # Read input
    if len(sys.argv) > 1 and sys.argv[1] not in ['-j', '-s']:
        filepath = sys.argv[1]
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        except FileNotFoundError:
            print(f'错误: 文件未找到 {filepath}', file=sys.stderr)
            sys.exit(1)
    else:
        text = sys.stdin.read()
    
    # Detect patterns
    issues, char_count = detect_patterns(text)
    score = calculate_score(issues, char_count)
    
    # Output results
    output = format_output(issues, char_count, score, as_json, score_only)
    print(output)

if __name__ == '__main__':
    main()
