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
            # Pick replacement based on casualness
            if casualness > 0.5 and len(alternatives) > 1:
                replacement = random.choice(alternatives)
            else:
                replacement = alternatives[0]
            text = text.replace(phrase, replacement, 1)  # Replace first occurrence
            # For subsequent occurrences, use different alternatives
            while phrase in text:
                replacement = random.choice(alternatives)
                text = text.replace(phrase, replacement, 1)
    
    return text

def merge_short_sentences(text, min_len=8):
    """Merge overly short consecutive sentences"""
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
    
    return ''.join(result)

def split_long_sentences(text, max_len=80):
    """Split overly long sentences at natural breakpoints"""
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
    
    return ''.join(result)

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
    
    # Pass 2: Sentence restructuring
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
    
    # Clean up artifacts
    text = re.sub(r'[，,]{2,}', '，', text)  # Remove double commas
    text = re.sub(r'[。]{2,}', '。', text)    # Remove double periods
    text = re.sub(r'\n{3,}', '\n\n', text)    # Normalize newlines
    text = re.sub(r'，。', '。', text)          # Remove comma before period
    text = re.sub(r'。，', '。', text)          # Remove period before comma
    
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
