#!/usr/bin/env python3
"""
Chinese AI Text Humanizer
Transforms AI-generated Chinese text to sound more natural
"""

import sys
import re
import random

# Replacement mappings
REPLACEMENTS = {
    '值得注意的是': ['注意', '要提醒的是', '特别说一下'],
    '综上所述': ['总之', '说到底', '简单讲'],
    '不难发现': ['可以看到', '很明显'],
    '总而言之': ['总之', '总的来说'],
    '与此同时': ['同时', '这时候'],
    '在此基础上': ['基于这个', '在这个基础上'],
    '由此可见': ['所以', '可见'],
    '此外': ['另外', '还有'],
    '需要指出的是': ['要说的是', '需要注意'],
    '值得一提的是': ['值得说的是', '还有一点'],
    '赋能': ['帮助', '提升', '支持'],
    '闭环': ['完整流程', '全链路'],
    '深度剖析': ['深入分析', '仔细看看'],
    '智慧时代': ['今天', '当下', '现在'],
    '数字化转型': ['数字化', '转型升级'],
    '助力': ['帮助', '支持'],
    '彰显': ['展现', '体现'],
    '凸显': ['突出', '显示'],
    '焕发': ['展现', '释放'],
}

# Scene-specific styles
SCENE_STYLES = {
    'social': {
        'add_casual_phrases': ['说实话', '没想到', '真的', '确实', '挺'],
        'add_emoji': True,
        'shorten_paragraphs': True,
    },
    'tech': {
        'keep_technical': True,
        'add_practical_phrases': ['实测', '踩过的坑', '实际使用中'],
    },
    'formal': {
        'keep_formal': True,
        'reduce_rhetoric': True,
    },
    'chat': {
        'conversational': True,
        'add_friendly_phrases': ['明白了', '好的', '没问题'],
    },
}

def remove_three_part_structure(text):
    """Remove 首先...其次...最后 patterns"""
    # Replace with natural transitions
    text = re.sub(r'首先[，,]\s*', '', text)
    text = re.sub(r'其次[，,]\s*', '另外，', text)
    text = re.sub(r'最后[，,]\s*', '还有，', text)
    
    # Remove 第一...第二...第三
    text = re.sub(r'第一[，,]\s*', '', text)
    text = re.sub(r'第二[，,]\s*', '接着，', text)
    text = re.sub(r'第三[，,]\s*', '然后，', text)
    
    return text

def replace_phrases(text, aggressive=False):
    """Replace AI phrases with natural alternatives"""
    for phrase, alternatives in REPLACEMENTS.items():
        if phrase in text:
            # Use random alternative for variety
            replacement = random.choice(alternatives) if aggressive else alternatives[0]
            text = text.replace(phrase, replacement)
    
    return text

def reduce_punctuation(text):
    """Reduce excessive punctuation"""
    # Limit em dashes
    segments = text.split('—')
    if len(segments) > 3:
        # Keep only first 2 em dashes
        text = segments[0] + '—' + segments[1] + '，' + '，'.join(segments[2:])
    
    # Replace excessive semicolons with commas
    text = re.sub(r'；', '，', text)
    
    return text

def vary_sentence_structure(text, aggressive=False):
    """Add variety to sentence structure"""
    if not aggressive:
        return text
    
    # Split into sentences
    sentences = re.split(r'([。！？])', text)
    result = []
    
    for i in range(0, len(sentences) - 1, 2):
        sentence = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        # Randomly add casual connectors
        if i > 0 and random.random() < 0.3:
            casual_connectors = ['不过', '但是', '而且', '另外']
            sentence = random.choice(casual_connectors) + '，' + sentence
        
        result.append(sentence + punct)
    
    return ''.join(result)

def add_colloquial_expressions(text, scene='general'):
    """Add colloquial expressions based on scene"""
    if scene == 'social':
        # Add casual phrases
        casual_phrases = ['说实话', '没想到', '确实']
        if random.random() < 0.3:
            first_sentence = text.split('。')[0]
            text = text.replace(first_sentence, random.choice(casual_phrases) + '，' + first_sentence, 1)
    
    elif scene == 'tech':
        # Add practical phrases
        practical = ['实测', '从经验来看', '实际使用中']
        if random.random() < 0.3:
            text = re.sub(r'(经过|通过)测试', random.choice(practical), text)
    
    return text

def shorten_paragraphs(text):
    """Break long paragraphs into shorter ones"""
    paragraphs = text.split('\n\n')
    result = []
    
    for para in paragraphs:
        if len(para) > 300:  # Long paragraph
            # Split at sentence boundaries
            sentences = re.split(r'([。！？])', para)
            chunks = []
            current_chunk = ''
            
            for i in range(0, len(sentences) - 1, 2):
                sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
                if len(current_chunk) + len(sentence) > 150:
                    chunks.append(current_chunk)
                    current_chunk = sentence
                else:
                    current_chunk += sentence
            
            if current_chunk:
                chunks.append(current_chunk)
            
            result.append('\n\n'.join(chunks))
        else:
            result.append(para)
    
    return '\n\n'.join(result)

def humanize(text, scene='general', aggressive=False):
    """Apply all humanization transformations"""
    # Step 1: Remove three-part structure
    text = remove_three_part_structure(text)
    
    # Step 2: Replace AI phrases
    text = replace_phrases(text, aggressive)
    
    # Step 3: Reduce punctuation
    text = reduce_punctuation(text)
    
    # Step 4: Vary sentence structure (if aggressive)
    if aggressive:
        text = vary_sentence_structure(text, aggressive)
    
    # Step 5: Add colloquial expressions
    text = add_colloquial_expressions(text, scene)
    
    # Step 6: Shorten paragraphs for social media
    if scene == 'social':
        text = shorten_paragraphs(text)
    
    return text

def main():
    # Parse arguments
    output_file = None
    scene = 'general'
    aggressive = False
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-o' and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]
            i += 2
        elif arg == '--scene' and i + 1 < len(sys.argv):
            scene = sys.argv[i + 1]
            i += 2
        elif arg == '-a':
            aggressive = True
            i += 1
        elif arg.startswith('-'):
            i += 1
        else:
            filepath = arg
            i += 1
    
    # Read input
    try:
        if 'filepath' in locals():
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            text = sys.stdin.read()
    except FileNotFoundError:
        print(f'错误: 文件未找到 {filepath}', file=sys.stderr)
        sys.exit(1)
    
    # Humanize text
    result = humanize(text, scene, aggressive)
    
    # Output
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'已保存到 {output_file}')
    else:
        print(result)

if __name__ == '__main__':
    main()
