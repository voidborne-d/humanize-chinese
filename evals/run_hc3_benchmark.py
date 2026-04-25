#!/usr/bin/env python3
"""
HC3-Chinese 回归评测。

跑 humanize-chinese 的 detect / humanize / academic 在 HC3-Chinese 子集上，
输出：
  1. 检测器能否区分 Human vs ChatGPT（分数分布 + AUC 代理）
  2. humanize 能否把 ChatGPT 文本的分数降到更接近 Human 区间
  3. 结构校验：段落保留率、长度保留率、重复子句率

HC3-Chinese 数据集：https://github.com/Hello-SimpleAI/chatgpt-comparison-detection
预期文件路径：../../data/hc3_chinese_all.jsonl（下载命令见 README）

Usage:
  python evals/run_hc3_benchmark.py                    # 默认 50 样本
  python evals/run_hc3_benchmark.py --n 100            # 100 样本
  python evals/run_hc3_benchmark.py --academic         # 用 academic_cn 而非 humanize_cn
  python evals/run_hc3_benchmark.py --source baike     # 只跑 baike
  python evals/run_hc3_benchmark.py -o report.json     # JSON 输出
"""

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import humanize_cn
from detect_cn import detect_patterns, calculate_score, score_to_level
from humanize_cn import humanize as humanize_general
from academic_cn import humanize_academic


DEFAULT_HC3_PATH = os.path.join(
    os.path.dirname(os.path.dirname(ROOT)),
    'data', 'hc3_chinese_all.jsonl'
)


def load_hc3(path, n=50, source_filter=None, min_chars=100, seed=42):
    """Load balanced sample from HC3-Chinese jsonl.

    Returns list of dicts with: question, human_answer, chatgpt_answer, source.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f'HC3-Chinese not found at {path}. Download with:\n'
            f'  mkdir -p {os.path.dirname(path)} && curl -L '
            f'"https://huggingface.co/datasets/Hello-SimpleAI/HC3-Chinese/'
            f'resolve/main/all.jsonl" -o {path}'
        )

    buckets = defaultdict(list)
    with open(path) as f:
        for line in f:
            obj = json.loads(line)
            source = obj.get('source', 'unknown')
            if source_filter and source != source_filter:
                continue
            h_answers = [a for a in (obj.get('human_answers') or []) if a]
            c_answers = [a for a in (obj.get('chatgpt_answers') or []) if a]
            if not h_answers or not c_answers:
                continue
            human = h_answers[0].strip()
            chatgpt = c_answers[0].strip()
            if len(human) < min_chars or len(chatgpt) < min_chars:
                continue
            buckets[source].append({
                'question': obj.get('question', '').strip(),
                'human_answer': human,
                'chatgpt_answer': chatgpt,
                'source': source,
            })

    rng = random.Random(seed)
    for bucket in buckets.values():
        rng.shuffle(bucket)

    if source_filter:
        samples = list(buckets.get(source_filter, []))[:n]
    else:
        # Balanced sample across sources (round-robin)
        samples = []
        sources = sorted(buckets.keys())
        round_i = 0
        while len(samples) < n:
            added = False
            for s in sources:
                if len(samples) >= n:
                    break
                if round_i < len(buckets[s]):
                    samples.append(buckets[s][round_i])
                    added = True
            if not added:
                break
            round_i += 1
    return samples


_LR_AVAILABLE = None

def _have_lr():
    global _LR_AVAILABLE
    if _LR_AVAILABLE is None:
        try:
            from ngram_model import compute_lr_score
            from ngram_model import _load_lr_coef
            _LR_AVAILABLE = _load_lr_coef() is not None
        except Exception:
            _LR_AVAILABLE = False
    return _LR_AVAILABLE


def score_text(text, mode='fused'):
    """Score text. mode in {'fused', 'lr', 'rule'}.
    Fused = 0.2*rule + 0.8*LR (default)."""
    issues, metrics = detect_patterns(text)
    rule = calculate_score(issues, metrics)
    if mode == 'rule' or not _have_lr():
        return rule, issues, metrics
    from ngram_model import compute_lr_score
    lr_r = compute_lr_score(text)
    if lr_r is None:
        return rule, issues, metrics
    if mode == 'lr':
        return lr_r['score'], issues, metrics
    # default: fused
    return round(0.2 * rule + 0.8 * lr_r['score']), issues, metrics


def count_paragraphs(text):
    return sum(1 for p in text.split('\n\n') if p.strip())


def find_repeat_clauses(text, min_len=10, max_check=50):
    """Find clauses >= min_len chars that appear >=2 times in text. Returns list of (clause, count)."""
    clauses = set()
    for part in re.split(r'[，。！？；]', text):
        part = part.strip()
        if len(part) >= min_len:
            clauses.add(part)
    dupes = []
    for c in list(clauses)[:max_check]:
        cnt = text.count(c)
        if cnt >= 2:
            dupes.append((c[:40], cnt))
    return dupes


# Grammar/register defects mirror the longform benchmark — these are bugs the
# cycle 22-34 J-path sweep already eliminated; the metric guards against
# regressions if a future change re-introduces any of them.
_DEFECT_PATTERNS = (
    (r'地地', 'doubled_di'),
    (r'的的', 'doubled_de'),
    (r'是是', 'doubled_shi'),
    (r'的地', 'mixed_de_di'),
    (r'可以地', 'awkward_keyi_di'),
    (r'有办法地', 'awkward_youbanfa_di'),
    (r'有效地能', 'inverted_youxiao_neng'),
    (r'跟进着', 'invalid_genjin_zhe'),
    (r'留着神', 'typo_liuzhe_shen'),
    (r'在[一-鿿]{1,4}左右下', 'idiom_break_yingxiang_zuoyou'),
    (r'案[察觉识看][觉破察出]场', 'idiom_break_anfa_xianchang'),
    (r'阵地地位', 'template13_zhendi_diwei'),
    (r'至关关键', 'idiom_break_zhiguan_zhongyao'),
    (r'最最要紧', 'doubled_zui'),
    (r'到到头来', 'doubled_dao'),
    (r'在在', 'doubled_zai'),
    (r'市场场景', 'doubled_chang'),
    (r'可以以', 'doubled_yi'),
)


def _count_grammar_defects(humanized, source):
    """Count humanize-introduced grammar defect patterns (vs source baseline)."""
    total = 0
    for pattern, _ in _DEFECT_PATTERNS:
        n_in = len(re.findall(pattern, source))
        n_out = len(re.findall(pattern, humanized))
        if n_out > n_in:
            total += (n_out - n_in)
    return total


def run_one(sample, mode='humanize', score_mode='fused'):
    """Run detect on both answers, humanize the ChatGPT answer, detect again.

    Returns dict of per-sample metrics.
    """
    human_score, _, _ = score_text(sample['human_answer'], mode=score_mode)
    chatgpt_score, _, _ = score_text(sample['chatgpt_answer'], mode=score_mode)

    original = sample['chatgpt_answer']
    if mode == 'academic':
        humanized = humanize_academic(original, aggressive=False, seed=42)
    else:
        humanized = humanize_general(original, scene='general', aggressive=False, seed=42)
    humanized_score, _, _ = score_text(humanized, mode=score_mode)

    paragraphs_before = count_paragraphs(original)
    paragraphs_after = count_paragraphs(humanized)
    length_ratio = len(humanized) / len(original) if len(original) else 0
    duplicates = find_repeat_clauses(humanized)
    grammar_defects = _count_grammar_defects(humanized, original)

    return {
        'source': sample['source'],
        'human_score': human_score,
        'chatgpt_score': chatgpt_score,
        'humanized_score': humanized_score,
        'delta': chatgpt_score - humanized_score,
        'paragraphs_before': paragraphs_before,
        'paragraphs_after': paragraphs_after,
        'paragraph_preserved': paragraphs_after >= paragraphs_before,
        'length_ratio': length_ratio,
        'duplicate_count': len(duplicates),
        'duplicates': duplicates[:3],
        'grammar_defects': grammar_defects,
    }


def summarize(results, mode):
    n = len(results)
    if n == 0:
        return {'error': 'no results'}

    # Separation: how often is human score LESS than chatgpt score
    human_scores = [r['human_score'] for r in results]
    chatgpt_scores = [r['chatgpt_score'] for r in results]
    humanized_scores = [r['humanized_score'] for r in results]
    deltas = [r['delta'] for r in results]

    correct_separation = sum(1 for h, c in zip(human_scores, chatgpt_scores) if h < c)

    by_source = defaultdict(list)
    for r in results:
        by_source[r['source']].append(r)

    source_summary = {}
    for src, rs in by_source.items():
        source_summary[src] = {
            'n': len(rs),
            'avg_human_score': round(sum(r['human_score'] for r in rs) / len(rs), 1),
            'avg_chatgpt_score': round(sum(r['chatgpt_score'] for r in rs) / len(rs), 1),
            'avg_humanized_score': round(sum(r['humanized_score'] for r in rs) / len(rs), 1),
            'avg_delta': round(sum(r['delta'] for r in rs) / len(rs), 1),
        }

    return {
        'n': n,
        'mode': mode,
        'detector_separation': {
            'correct_rate': round(correct_separation / n, 3),
            'avg_human_score': round(sum(human_scores) / n, 1),
            'avg_chatgpt_score': round(sum(chatgpt_scores) / n, 1),
            'score_gap': round((sum(chatgpt_scores) - sum(human_scores)) / n, 1),
        },
        'humanizer_effect': {
            'avg_delta': round(sum(deltas) / n, 1),
            'median_delta': sorted(deltas)[n // 2],
            'min_delta': min(deltas),
            'max_delta': max(deltas),
            'moved_toward_human': sum(
                1 for r in results if r['humanized_score'] < r['chatgpt_score']
            ),
            'moved_below_chatgpt_avg': sum(
                1 for r in results
                if r['humanized_score'] < sum(chatgpt_scores) / n
            ),
        },
        'structure_health': {
            'paragraph_preserved_rate': round(
                sum(r['paragraph_preserved'] for r in results) / n, 3
            ),
            'avg_length_ratio': round(
                sum(r['length_ratio'] for r in results) / n, 3
            ),
            'samples_with_duplicates': sum(1 for r in results if r['duplicate_count']),
            # Hard-floor metric: humanize-introduced grammar defects (doubled
            # chars / typos / idiom corruption / invalid transitions). Cycle
            # 22-34 J-path sweep brought this to 0; metric guards regressions.
            'grammar_defects_count': sum(
                r.get('grammar_defects', 0) for r in results
            ),
            'grammar_defects_samples': sum(
                1 for r in results if r.get('grammar_defects', 0) > 0
            ),
        },
        'by_source': source_summary,
    }


def format_text_report(summary):
    lines = []
    lines.append('═══ HC3-Chinese 基准测试 ═══')
    lines.append(f'样本数: {summary["n"]} | 模式: {summary["mode"]}')
    lines.append('')
    lines.append('── 检测器区分力 ──')
    ds = summary['detector_separation']
    lines.append(f'  人类 vs AI 正确分离率: {ds["correct_rate"] * 100:.1f}%')
    lines.append(f'  人类平均分: {ds["avg_human_score"]} | ChatGPT 平均分: {ds["avg_chatgpt_score"]}')
    lines.append(f'  分数差距: {ds["score_gap"]} 分（越大说明检测器越能区分）')
    lines.append('')
    lines.append('── humanize 效果 ──')
    he = summary['humanizer_effect']
    lines.append(f'  平均降幅: {he["avg_delta"]} 分 | 中位数: {he["median_delta"]}')
    lines.append(f'  范围: {he["min_delta"]} 到 {he["max_delta"]}')
    lines.append(f'  有降低的样本: {he["moved_toward_human"]}/{summary["n"]}')
    lines.append('')
    lines.append('── 结构健康 ──')
    sh = summary['structure_health']
    lines.append(f'  段落保留率: {sh["paragraph_preserved_rate"] * 100:.1f}%')
    lines.append(f'  平均长度比 (改写后/原文): {sh["avg_length_ratio"]}')
    lines.append(f'  有重复子句的样本: {sh["samples_with_duplicates"]}')
    gd_count = sh.get('grammar_defects_count', 0)
    gd_samples = sh.get('grammar_defects_samples', 0)
    lines.append(f'  grammar defects (humanize-introduced): {gd_count} 处 in {gd_samples} 样本'
                 f' {"✓" if gd_count == 0 else "⚠"}')
    lines.append('')
    lines.append('── 按来源 ──')
    for src, info in summary['by_source'].items():
        lines.append(
            f'  {src:12s} n={info["n"]:3d} | '
            f'human={info["avg_human_score"]:5.1f} | '
            f'ChatGPT={info["avg_chatgpt_score"]:5.1f} → {info["avg_humanized_score"]:5.1f} '
            f'(降 {info["avg_delta"]:+.1f})'
        )
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='HC3-Chinese benchmark for humanize-chinese')
    parser.add_argument('--data', default=DEFAULT_HC3_PATH,
                       help=f'HC3-Chinese jsonl path (default: {DEFAULT_HC3_PATH})')
    parser.add_argument('--n', type=int, default=50, help='样本数 (default: 50)')
    parser.add_argument('--source', help='仅跑某一来源 (baike/open_qa/medicine/...)')
    parser.add_argument('--academic', action='store_true',
                       help='用 academic_cn humanize（默认 humanize_cn general 场景）')
    parser.add_argument('--cilin', action='store_true',
                       help='启用 CiLin 同义词词林扩展候选')
    parser.add_argument('-o', '--output', help='JSON 输出文件')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='每个样本逐条打印')
    parser.add_argument('--seed', type=int, default=42, help='随机种子')
    parser.add_argument('--mode', default='fused', choices=['fused', 'lr', 'rule'],
                        help='score mode (default: fused = 0.2*rule + 0.8*LR)')
    args = parser.parse_args()

    if args.cilin:
        humanize_cn._USE_CILIN = True

    samples = load_hc3(args.data, n=args.n, source_filter=args.source, seed=args.seed)
    if not samples:
        print('错误: 没有符合条件的样本', file=sys.stderr)
        sys.exit(1)

    mode = 'academic' if args.academic else 'humanize'
    results = []
    for i, sample in enumerate(samples):
        r = run_one(sample, mode=mode, score_mode=args.mode)
        results.append(r)
        if args.verbose:
            print(f'[{i+1}/{len(samples)}] {r["source"]:12s} '
                  f'human={r["human_score"]:3d} '
                  f'ChatGPT={r["chatgpt_score"]:3d} → {r["humanized_score"]:3d} '
                  f'(降 {r["delta"]:+3d}) '
                  f'段{r["paragraphs_before"]}→{r["paragraphs_after"]}'
                  + (' DUP!' if r['duplicate_count'] else ''))
        elif (i + 1) % 10 == 0:
            print(f'  ... {i+1}/{len(samples)} done', file=sys.stderr)

    summary = summarize(results, mode)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump({'summary': summary, 'samples': results}, f,
                     ensure_ascii=False, indent=2)
        print(f'✓ 已保存到 {args.output}', file=sys.stderr)

    print(format_text_report(summary))


if __name__ == '__main__':
    main()
