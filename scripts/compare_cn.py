#!/usr/bin/env python3
"""
Compare AI detection scores before and after humanization
"""

import sys
import subprocess
import os

def run_detect(text):
    """Run detect_cn.py and get score"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    detect_script = os.path.join(script_dir, 'detect_cn.py')
    
    try:
        result = subprocess.run(
            ['python3', detect_script, '-s'],
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=10
        )
        return result.stdout.decode('utf-8').strip()
    except Exception as e:
        return f'error: {e}'

def run_humanize(text, scene='general', aggressive=False):
    """Run humanize_cn.py and get result"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    humanize_script = os.path.join(script_dir, 'humanize_cn.py')
    
    cmd = ['python3', humanize_script, '--scene', scene]
    if aggressive:
        cmd.append('-a')
    
    try:
        result = subprocess.run(
            cmd,
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=10
        )
        return result.stdout.decode('utf-8')
    except Exception as e:
        return f'error: {e}'

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
                original_text = f.read()
        else:
            original_text = sys.stdin.read()
    except FileNotFoundError:
        print(f'错误: 文件未找到 {filepath}', file=sys.stderr)
        sys.exit(1)
    
    # Get original score
    print('正在检测原文...')
    original_score = run_detect(original_text)
    
    # Humanize
    print('正在人类化改写...')
    humanized_text = run_humanize(original_text, scene, aggressive)
    
    # Get new score
    print('正在检测改写后...')
    new_score = run_detect(humanized_text)
    
    # Show comparison
    print('\n=== 对比结果 ===\n')
    print(f'原文 AI 概率: {original_score}')
    print(f'改写后 AI 概率: {new_score}')
    print()
    
    # Improvement assessment
    score_levels = {'low': 0, 'medium': 1, 'high': 2, 'very high': 3}
    original_level = score_levels.get(original_score, -1)
    new_level = score_levels.get(new_score, -1)
    
    if new_level < original_level:
        improvement = original_level - new_level
        print(f'✅ 改善了 {improvement} 个等级')
    elif new_level == original_level:
        print('⚠️  等级未变化（可能需要手动优化）')
    else:
        print('❌ 检测等级上升（不太可能）')
    
    print()
    
    # Save output
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(humanized_text)
        print(f'改写结果已保存到: {output_file}')
    else:
        print('=== 改写后文本 ===\n')
        print(humanized_text)

if __name__ == '__main__':
    main()
