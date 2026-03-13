#!/usr/bin/env python3
"""
Compare AI detection scores before and after humanization v2.0
Shows detailed diff of score changes by category
"""

import sys
import subprocess
import os
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_detect(text, as_json=True):
    """Run detect_cn.py and get results"""
    detect_script = os.path.join(SCRIPT_DIR, 'detect_cn.py')
    cmd = ['python3', detect_script]
    if as_json:
        cmd.append('-j')
    
    try:
        result = subprocess.run(
            cmd, input=text, capture_output=True,
            text=True, encoding='utf-8', timeout=30
        )
        if as_json and result.returncode == 0:
            return json.loads(result.stdout)
        return result.stdout.strip()
    except Exception as e:
        return {'error': str(e)}

def run_humanize(text, scene='general', aggressive=False, style=None):
    """Run humanize_cn.py and get result"""
    humanize_script = os.path.join(SCRIPT_DIR, 'humanize_cn.py')
    cmd = ['python3', humanize_script, '--scene', scene]
    if aggressive:
        cmd.append('-a')
    if style:
        cmd.extend(['--style', style])
    
    try:
        result = subprocess.run(
            cmd, input=text, capture_output=True,
            text=True, encoding='utf-8', timeout=30
        )
        return result.stdout
    except Exception as e:
        return f'error: {e}'

def format_comparison(before, after):
    """Format detailed comparison"""
    lines = []
    
    b_score = before.get('score', 0)
    a_score = after.get('score', 0)
    b_level = before.get('level', 'unknown')
    a_level = after.get('level', 'unknown')
    
    # Score comparison bar
    b_bar_len = int(b_score / 100 * 20)
    a_bar_len = int(a_score / 100 * 20)
    
    lines.append('═══ 对比结果 ═══\n')
    lines.append(f'原文:   {b_score:3d}/100 [{"█" * b_bar_len}{"░" * (20 - b_bar_len)}] {b_level.upper()}')
    lines.append(f'改写后: {a_score:3d}/100 [{"█" * a_bar_len}{"░" * (20 - a_bar_len)}] {a_level.upper()}')
    
    diff = b_score - a_score
    if diff > 0:
        lines.append(f'\n✅ 降低了 {diff} 分')
    elif diff == 0:
        lines.append(f'\n⚠️  分数未变化')
    else:
        lines.append(f'\n❌ 分数上升了 {abs(diff)} 分')
    
    # Category breakdown
    b_issues = before.get('issues', {})
    a_issues = after.get('issues', {})
    all_cats = set(list(b_issues.keys()) + list(a_issues.keys()))
    
    if all_cats:
        lines.append('\n── 分类变化 ──')
        for cat in sorted(all_cats):
            b_count = len(b_issues.get(cat, []))
            a_count = len(a_issues.get(cat, []))
            
            if b_count == 0 and a_count == 0:
                continue
            
            if a_count < b_count:
                status = '✅'
            elif a_count == b_count:
                status = '➖'
            else:
                status = '❌'
            
            lines.append(f'  {status} {cat}: {b_count} → {a_count}')
    
    # Metrics comparison
    b_metrics = before.get('metrics', {})
    a_metrics = after.get('metrics', {})
    
    if b_metrics and a_metrics:
        lines.append('\n── 指标变化 ──')
        b_emo = b_metrics.get('emotional_density', 0)
        a_emo = a_metrics.get('emotional_density', 0)
        lines.append(f'  情感密度: {b_emo:.2f}% → {a_emo:.2f}%')
        
        b_ent = b_metrics.get('entropy')
        a_ent = a_metrics.get('entropy')
        if b_ent and a_ent:
            lines.append(f'  信息熵:   {b_ent:.2f} → {a_ent:.2f}')
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(description='中文 AI 文本对比分析 v2.0')
    parser.add_argument('file', nargs='?', help='输入文件路径')
    parser.add_argument('-o', '--output', help='保存改写结果')
    parser.add_argument('--scene', default='general',
                       choices=['general', 'social', 'tech', 'formal', 'chat'],
                       help='场景')
    parser.add_argument('--style', help='写作风格')
    parser.add_argument('-a', '--aggressive', action='store_true', help='激进模式')
    
    args = parser.parse_args()
    
    # Read input
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                original_text = f.read()
        except FileNotFoundError:
            print(f'错误: 文件未找到 {args.file}', file=sys.stderr)
            sys.exit(1)
    else:
        original_text = sys.stdin.read()
    
    if not original_text.strip():
        print('错误: 输入为空', file=sys.stderr)
        sys.exit(1)
    
    # Detect original
    print('⏳ 检测原文...')
    before = run_detect(original_text, as_json=True)
    
    # Humanize
    print('⏳ 人性化改写...')
    humanized_text = run_humanize(original_text, args.scene, args.aggressive, args.style)
    
    # Detect humanized
    print('⏳ 检测改写后...')
    after = run_detect(humanized_text, as_json=True)
    
    # Show comparison
    if isinstance(before, dict) and isinstance(after, dict) and 'error' not in before:
        print(format_comparison(before, after))
    else:
        print(f'\n原文分数: {before}')
        print(f'改写后分数: {after}')
    
    # Save output
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(humanized_text)
        print(f'\n改写结果已保存到: {args.output}')
    else:
        print('\n═══ 改写后文本 ═══\n')
        print(humanized_text)

if __name__ == '__main__':
    main()
