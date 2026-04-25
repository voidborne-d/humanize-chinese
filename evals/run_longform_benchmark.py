#!/usr/bin/env python3
"""
长文本 (longform) 回归评测 — M-path harness.

评测 humanize-chinese 在长篇创作（小说/学术/新闻/博客/评论）上的表现：
  1. detector --scene novel 下 AI 长文本 vs 人类长文本的区分力
  2. humanize 后 AI 长文本的分数能否向人类分布靠拢
  3. 段落结构是否保留（M-0 修复后关键指标）

数据源（均在 ../../data/）:
  - ai_longform_corpus.jsonl    170 条 AI 长文本 (5 LLM × 5 genre)
  - human_novel_corpus.jsonl    人类小说 (v3ucn)
  - human_news_corpus.jsonl     人类新闻 (CNewSum)

Usage:
  python evals/run_longform_benchmark.py                 # 默认全部 170
  python evals/run_longform_benchmark.py --n 60          # 60 样本
  python evals/run_longform_benchmark.py --genre novel   # 只跑 novel
  python evals/run_longform_benchmark.py --model claude-sonnet-4
  python evals/run_longform_benchmark.py -o report.json
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
DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(ROOT)), 'data')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from detect_cn import detect_patterns, calculate_score
from humanize_cn import humanize as humanize_general

AI_CORPUS = os.path.join(DATA_ROOT, 'ai_longform_corpus.jsonl')
HUMAN_NOVEL = os.path.join(DATA_ROOT, 'human_novel_corpus.jsonl')
HUMAN_NEWS = os.path.join(DATA_ROOT, 'human_news_corpus.jsonl')


def load_ai_longform(path=AI_CORPUS, n=None, genre=None, model=None, seed=42):
    if not os.path.exists(path):
        raise FileNotFoundError(f'AI longform corpus not found at {path}')
    items = []
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            if genre and o.get('genre') != genre:
                continue
            if model and model not in o.get('model', ''):
                continue
            items.append(o)
    rng = random.Random(seed)
    rng.shuffle(items)
    if n is not None:
        items = items[:n]
    return items


def load_human_longform(n=None, seed=42):
    """Load human novel + news, balanced."""
    items = []
    for path in (HUMAN_NOVEL, HUMAN_NEWS):
        if not os.path.exists(path):
            continue
        with open(path) as f:
            for line in f:
                items.append(json.loads(line))
    rng = random.Random(seed)
    rng.shuffle(items)
    if n is not None:
        items = items[:n]
    return items


def score_longform(text, scene='novel'):
    """Fused score with scene-specific LR (novel scene for longform)."""
    issues, metrics = detect_patterns(text)
    rule = calculate_score(issues, metrics)
    try:
        from ngram_model import compute_lr_score
        lr_r = compute_lr_score(text, scene=scene)
    except Exception:
        lr_r = None
    if lr_r is None:
        return rule
    return round(0.2 * rule + 0.8 * lr_r['score'])


def count_paragraphs(text):
    return sum(1 for p in text.split('\n\n') if p.strip())


# Quality issue patterns — residual 观感 violations after humanize.
# Each set targets a specific class of awkwardness flagged by Petalses
# issue #5 / cycle 7-11 narrative diagnostics.
_REACTION_FRAGMENTS = (
    '颇有道理。', '难以一概。', '事出有因。', '耐人寻味。',
    '值得深思。', '让人深思。', '可见一斑。', '有一定道理。',
    '各有道理。', '一言难尽。', '说来话长。', '不无道理。',
)
_FIRST_PERSON_INTRUSION = (
    '在我看来，', '我觉得，', '依我之见，', '讲真，',
    '当然了，', '怎么说呢，', '不瞒你说，', '说到底，',
)


def count_quality_issues(text):
    """Count residual 观感 violations in humanize output."""
    return {
        'reaction_fragments': sum(text.count(r) for r in _REACTION_FRAGMENTS),
        'first_person_intrusion': sum(text.count(p) for p in _FIRST_PERSON_INTRUSION),
    }


def run_one_ai(sample, seed=42, best_of_n=0, humanize_style=None):
    orig = sample['text']
    orig_score = score_longform(orig, scene='novel')
    humanized = humanize_general(orig, scene='general', aggressive=False,
                                 seed=seed, best_of_n=best_of_n,
                                 style=humanize_style)
    humanized_score = score_longform(humanized, scene='novel')
    p_before = count_paragraphs(orig)
    p_after = count_paragraphs(humanized)
    length_ratio = len(humanized) / len(orig) if len(orig) else 0
    quality = count_quality_issues(humanized)
    return {
        'model': sample.get('model', '?'),
        'genre': sample.get('genre', '?'),
        'cn_chars': sample.get('cn_chars', len(orig)),
        'orig_score': orig_score,
        'humanized_score': humanized_score,
        'delta': orig_score - humanized_score,
        'paragraphs_before': p_before,
        'paragraphs_after': p_after,
        'paragraph_preserved': p_after >= p_before,
        'length_ratio': length_ratio,
        'reaction_fragments': quality['reaction_fragments'],
        'first_person_intrusion': quality['first_person_intrusion'],
    }


def run_one_human(sample):
    text = sample.get('text', '')
    return {
        'genre': sample.get('genre', '?'),
        'source': sample.get('source', '?'),
        'score': score_longform(text, scene='novel'),
        'cn_chars': len(text),
    }


def summarize(ai_results, human_results):
    n_ai = len(ai_results)
    n_h = len(human_results)
    if n_ai == 0:
        return {'error': 'no AI results'}

    deltas = [r['delta'] for r in ai_results]
    orig_scores = [r['orig_score'] for r in ai_results]
    humanized_scores = [r['humanized_score'] for r in ai_results]
    human_scores = [r['score'] for r in human_results]

    # Per-genre
    by_genre = defaultdict(list)
    for r in ai_results:
        by_genre[r['genre']].append(r)
    genre_summary = {}
    for g, rs in by_genre.items():
        genre_summary[g] = {
            'n': len(rs),
            'avg_orig': round(sum(r['orig_score'] for r in rs) / len(rs), 1),
            'avg_humanized': round(sum(r['humanized_score'] for r in rs) / len(rs), 1),
            'avg_delta': round(sum(r['delta'] for r in rs) / len(rs), 1),
            'paragraph_preserved_rate': round(
                sum(r['paragraph_preserved'] for r in rs) / len(rs), 3
            ),
        }

    # Per-model
    by_model = defaultdict(list)
    for r in ai_results:
        by_model[r['model']].append(r)
    model_summary = {}
    for m, rs in by_model.items():
        model_summary[m] = {
            'n': len(rs),
            'avg_orig': round(sum(r['orig_score'] for r in rs) / len(rs), 1),
            'avg_humanized': round(sum(r['humanized_score'] for r in rs) / len(rs), 1),
            'avg_delta': round(sum(r['delta'] for r in rs) / len(rs), 1),
        }

    # Detector separation (human vs AI orig)
    if n_h > 0:
        avg_human = sum(human_scores) / n_h
    else:
        avg_human = 0
    avg_ai_orig = sum(orig_scores) / n_ai
    gap = avg_ai_orig - avg_human

    return {
        'n_ai': n_ai,
        'n_human': n_h,
        'detector_separation': {
            'avg_human_score': round(avg_human, 1),
            'avg_ai_orig': round(avg_ai_orig, 1),
            'score_gap': round(gap, 1),
        },
        'humanizer_effect': {
            'avg_delta': round(sum(deltas) / n_ai, 1),
            'median_delta': sorted(deltas)[n_ai // 2],
            'min_delta': min(deltas),
            'max_delta': max(deltas),
            'moved_toward_human': sum(1 for r in ai_results
                                       if r['humanized_score'] < r['orig_score']),
            'avg_humanized': round(sum(humanized_scores) / n_ai, 1),
        },
        'structure_health': {
            'paragraph_preserved_rate': round(
                sum(r['paragraph_preserved'] for r in ai_results) / n_ai, 3
            ),
            'avg_length_ratio': round(
                sum(r['length_ratio'] for r in ai_results) / n_ai, 3
            ),
            # Marker occurrence counts (essay-register markers added by
            # noise/reaction injection). For dialogue-heavy text these are
            # 观感 violations (cycle 7/8/11 narrative guards already filter
            # those). For pure essay/blog text these are register-appropriate.
            'reaction_marker_count': sum(
                r.get('reaction_fragments', 0) for r in ai_results
            ),
            'first_person_marker_count': sum(
                r.get('first_person_intrusion', 0) for r in ai_results
            ),
        },
        'by_genre': genre_summary,
        'by_model': model_summary,
    }


def print_report(summary):
    print(f'═══ Longform 基准测试 ═══')
    print(f"样本数: AI={summary['n_ai']} human={summary['n_human']} | scene=novel")
    print()
    print('── 检测器区分力 (--scene novel) ──')
    ds = summary['detector_separation']
    print(f"  人类平均分: {ds['avg_human_score']} | AI 原平均分: {ds['avg_ai_orig']}")
    print(f"  gap: {ds['score_gap']} (越大越能区分)")
    print()
    print('── humanize 效果 ──')
    he = summary['humanizer_effect']
    print(f"  平均降幅: {he['avg_delta']} | 中位: {he['median_delta']} | 范围 [{he['min_delta']}, {he['max_delta']}]")
    print(f"  降分样本: {he['moved_toward_human']}/{summary['n_ai']} | 平均改后分: {he['avg_humanized']}")
    print()
    print('── 结构健康 ──')
    sh = summary['structure_health']
    print(f"  段落保留率: {sh['paragraph_preserved_rate']*100:.1f}%")
    print(f"  平均长度比 (改写后/原文): {sh['avg_length_ratio']}")
    print(f"  essay-register markers: reaction={sh.get('reaction_marker_count', 0)} / "
          f"1st-person={sh.get('first_person_marker_count', 0)} 处")
    print(f"  (narrative-heavy 观感 violations 已由 dialogue density guard 过滤；这些数字"
          f"主要反映 essay/academic/blog register-appropriate insertions)")
    print()
    print('── 按 genre ──')
    for g, s in sorted(summary['by_genre'].items()):
        print(f"  {g:10s} n={s['n']:3d} | orig={s['avg_orig']:5.1f} → {s['avg_humanized']:5.1f} "
              f"(Δ {s['avg_delta']:+5.1f}) | 段留={s['paragraph_preserved_rate']*100:.0f}%")
    print()
    print('── 按 model ──')
    for m, s in sorted(summary['by_model'].items()):
        short_m = m.split('/')[-1] if '/' in m else m
        print(f"  {short_m:25s} n={s['n']:3d} | orig={s['avg_orig']:5.1f} → {s['avg_humanized']:5.1f} (Δ {s['avg_delta']:+5.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=None, help='AI sample size (default all 170)')
    ap.add_argument('--n-human', type=int, default=60, help='human sample size (default 60)')
    ap.add_argument('--genre', help='filter AI by genre: novel/academic/news/blog/review')
    ap.add_argument('--model', help='filter AI by model substring')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--best-of-n', type=int, default=0,
                    help='humanize best-of-n (0 = single seed, default 0 for speed)')
    ap.add_argument('--humanize-style', default=None,
                    help='pass style kwarg to humanize() — e.g. "novel" routes '
                         'novel-register narrative-safe filters (skip noise '
                         'inject, novel-aware bigram blacklist). Default None '
                         'matches the production humanize(scene="general") path.')
    ap.add_argument('-o', '--output', help='save JSON report to file')
    args = ap.parse_args()

    print(f'Loading AI longform...')
    ai = load_ai_longform(n=args.n, genre=args.genre, model=args.model, seed=args.seed)
    print(f'  loaded {len(ai)} AI samples')

    print(f'Loading human longform...')
    hu = load_human_longform(n=args.n_human, seed=args.seed)
    print(f'  loaded {len(hu)} human samples')

    print(f'Scoring human baseline...')
    human_results = [run_one_human(s) for s in hu]

    print(f'Humanizing + scoring AI...')
    ai_results = []
    for i, s in enumerate(ai, 1):
        if i % 10 == 0:
            print(f'  ... {i}/{len(ai)} done')
        try:
            ai_results.append(run_one_ai(s, seed=args.seed,
                                          best_of_n=args.best_of_n,
                                          humanize_style=args.humanize_style))
        except Exception as e:
            print(f'  ! sample {i} failed: {e}')

    summary = summarize(ai_results, human_results)
    print_report(summary)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump({
                'summary': summary,
                'ai_results': ai_results,
                'human_results': human_results,
            }, f, ensure_ascii=False, indent=2)
        print(f'\nReport saved to {args.output}')


if __name__ == '__main__':
    main()
