#!/usr/bin/env python3
"""Long-form scene LR trainer.

Trains a logistic regression with `ngram_model.LR_FEATURE_NAMES` on
the long-form corpus only (AI long-form + human novel + human news),
and writes the coefficients to `scripts/lr_coef_longform.json`.

Distinguished from `train_lr_multisource.py` (general LR which mixes
HC3 / CUDRT / longform): this trainer is for the novel/longform scene
dispatched by `_auto_scene` (>=1500 cn chars) and benefits from
features that only fire on multi-paragraph text.

Usage:
  python3 scripts/train_lr_longform.py
  python3 scripts/train_lr_longform.py --n-ai 170 --n-human 170 --c 1.0
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from statistics import mean, stdev

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
WORKSPACE = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, SCRIPT_DIR)

import ngram_model as nm

AI_LONGFORM_PATH = os.path.join(WORKSPACE, 'data/ai_longform_corpus.jsonl')
HUMAN_NOVEL_PATH = os.path.join(WORKSPACE, 'data/human_novel_corpus.jsonl')
HUMAN_NEWS_PATH = os.path.join(WORKSPACE, 'data/human_news_corpus.jsonl')
HUMAN_NEWS_MULTIPARA_PATH = os.path.join(
    WORKSPACE, 'data/human_news_multipara_corpus.jsonl')
# cycle 196: cudrt + m4 OOD human samples (234 total: 200 long
# business news + 34 long QA), opt-in via --n-human-misc.
HUMAN_MISC_PATH = os.path.join(WORKSPACE, 'data/human_misc_corpus.jsonl')
# cycle 217: m4/cudrt OOD AI samples (157 long >=500 cn). Opt-in via
# --n-ai-misc to expand AI training pool from 170 → 327 max.
M4_PATH = os.path.join(WORKSPACE, 'data/m4_zh_ood.jsonl')
CUDRT_PATH = os.path.join(WORKSPACE, 'data/cudrt_zh_ood.jsonl')
DEFAULT_OUT = os.path.join(SCRIPT_DIR, 'lr_coef_longform.json')


def _cn(t: str) -> int:
    return sum(1 for c in t if '一' <= c <= '鿿')


def _para_count(t: str, min_para_cn: int = 30) -> int:
    """Number of multi-character paragraphs (split on \\n\\n)."""
    import re
    raw = re.split(r'\n\s*\n', t)
    return sum(1 for p in raw if p.strip() and _cn(p) >= min_para_cn)


def _load_jsonl(path: str, min_cn: int, min_paras: int = 0,
                target_label: int | None = None) -> list[str]:
    """Load text samples from jsonl. If target_label is set (0 or 1),
    filter by the 'label' field. None means no filter (default)."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                d = json.loads(line)
            except Exception:
                continue
            if target_label is not None:
                if d.get('label') != target_label:
                    continue
            t = d.get('text') or d.get('content') or ''
            if not t or _cn(t) < min_cn:
                continue
            if min_paras and _para_count(t) < min_paras:
                continue
            out.append(t)
    return out


def _take(seq: list[str], n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    items = list(seq)
    rng.shuffle(items)
    return items[:n]


def standardize(X_train, X_holdout):
    n_feat = len(X_train[0])
    means = [mean(x[f] for x in X_train) for f in range(n_feat)]
    scales = [(stdev([x[f] for x in X_train]) or 1.0) for f in range(n_feat)]

    def s(x):
        return [(x[f] - means[f]) / scales[f] for f in range(n_feat)]

    return [s(x) for x in X_train], [s(x) for x in X_holdout], means, scales


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--n-ai', type=int, default=170)
    ap.add_argument('--n-human-novel', type=int, default=100)
    ap.add_argument('--n-human-news', type=int, default=200)
    ap.add_argument('--n-human-news-multipara', type=int, default=0,
                    help='multi-paragraph THUCNews samples (cycle 147 corpus expansion)')
    ap.add_argument('--n-human-misc', type=int, default=0,
                    help='cudrt + m4 OOD human samples (cycle 196 corpus expansion). '
                         'Single-paragraph long business news + QA, 234 total.')
    ap.add_argument('--n-ai-misc', type=int, default=0,
                    help='cudrt + m4 OOD AI samples (cycle 217 corpus expansion). '
                         'Long-form AI text (>=500 cn), ~157 total.')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--c', type=float, default=1.0)
    ap.add_argument('--min-cn-ai', type=int, default=200)
    ap.add_argument('--min-cn-novel', type=int, default=400)
    ap.add_argument('--min-cn-news', type=int, default=600)
    ap.add_argument('--min-cn-misc', type=int, default=400)
    ap.add_argument('--min-paras', type=int, default=0,
                    help='if >0, keep only samples with at least this many '
                         'multi-character paragraphs (split on blank lines). '
                         'Recommended for v5 paragraph-level features.')
    args = ap.parse_args()

    print(f'Loading AI long-form (target n={args.n_ai})...')
    ai_pool = _load_jsonl(AI_LONGFORM_PATH, args.min_cn_ai,
                          min_paras=args.min_paras)
    ai = _take(ai_pool, args.n_ai, args.seed + 2)
    print(f'  AI long-form pool={len(ai_pool)}, taken={len(ai)}')

    ai_misc = []
    if args.n_ai_misc > 0:
        print(f'Loading AI misc (m4+cudrt label=1, target n={args.n_ai_misc})...')
        m4_ai = _load_jsonl(M4_PATH, args.min_cn_misc,
                            min_paras=args.min_paras, target_label=1)
        cudrt_ai = _load_jsonl(CUDRT_PATH, args.min_cn_misc,
                               min_paras=args.min_paras, target_label=1)
        ai_misc_pool = m4_ai + cudrt_ai
        ai_misc = _take(ai_misc_pool, args.n_ai_misc, args.seed + 7)
        print(f'  AI misc pool={len(ai_misc_pool)} (m4={len(m4_ai)}, '
              f'cudrt={len(cudrt_ai)}), taken={len(ai_misc)}')
        ai = ai + ai_misc

    print(f'Loading human novel (target n={args.n_human_novel})...')
    nov_pool = _load_jsonl(HUMAN_NOVEL_PATH, args.min_cn_novel,
                           min_paras=args.min_paras)
    nov = _take(nov_pool, args.n_human_novel, args.seed + 3)
    print(f'  Human novel pool={len(nov_pool)}, taken={len(nov)}')

    print(f'Loading human news (target n={args.n_human_news})...')
    nws_pool = _load_jsonl(HUMAN_NEWS_PATH, args.min_cn_news,
                           min_paras=args.min_paras)
    nws = _take(nws_pool, args.n_human_news, args.seed + 4)
    print(f'  Human news pool={len(nws_pool)}, taken={len(nws)}')

    print(f'Loading human news multi-para '
          f'(target n={args.n_human_news_multipara})...')
    nwsmp_pool = _load_jsonl(HUMAN_NEWS_MULTIPARA_PATH, args.min_cn_news,
                             min_paras=args.min_paras)
    nwsmp = _take(nwsmp_pool, args.n_human_news_multipara, args.seed + 5)
    print(f'  Human news multi-para pool={len(nwsmp_pool)}, taken={len(nwsmp)}')

    misc = []
    if args.n_human_misc > 0:
        print(f'Loading human misc (target n={args.n_human_misc})...')
        misc_pool = _load_jsonl(HUMAN_MISC_PATH, args.min_cn_misc,
                                min_paras=args.min_paras)
        misc = _take(misc_pool, args.n_human_misc, args.seed + 6)
        print(f'  Human misc pool={len(misc_pool)}, taken={len(misc)}')

    hum = nov + nws + nwsmp + misc
    n = min(len(ai), len(hum))
    ai = ai[:n]
    hum = hum[:n]
    print(f'Combined: {len(ai)} AI + {len(hum)} human (n={n} per class)')
    if n < 50:
        print('Refusing to train on n<50 per class — corpus too small.')
        sys.exit(1)

    print(f'Extracting features for {2*n} samples...')
    X, y = [], []
    for i, t in enumerate(ai):
        vec, _ = nm.extract_feature_vector(t)
        X.append(vec); y.append(1)
        if (i + 1) % 50 == 0:
            print(f'  AI {i+1}/{n}')
    for i, t in enumerate(hum):
        vec, _ = nm.extract_feature_vector(t)
        X.append(vec); y.append(0)
        if (i + 1) % 50 == 0:
            print(f'  Human {i+1}/{n}')

    rng = random.Random(args.seed)
    idx_ai = list(range(n))
    idx_h = list(range(n, 2 * n))
    rng.shuffle(idx_ai)
    rng.shuffle(idx_h)
    split = int(0.8 * n)
    train_idx = idx_ai[:split] + idx_h[:split]
    holdout_idx = idx_ai[split:] + idx_h[split:]
    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    X_holdout = [X[i] for i in holdout_idx]
    y_holdout = [y[i] for i in holdout_idx]
    print(f'Train: {len(X_train)}  Holdout: {len(X_holdout)}')

    X_train_std, X_holdout_std, means, scales = standardize(X_train, X_holdout)

    from sklearn.linear_model import LogisticRegression
    lr_model = LogisticRegression(C=args.c, penalty='l2', solver='lbfgs',
                                  max_iter=1000)
    lr_model.fit(X_train_std, y_train)
    w = list(lr_model.coef_[0])
    b = float(lr_model.intercept_[0])

    def predict(x):
        z = b + sum(x[i] * w[i] for i in range(len(w)))
        return 1.0 / (1.0 + math.exp(-z)) if z > -500 else 0.0

    p_holdout = [predict(x) for x in X_holdout_std]
    correct = sum(1 for p, yy in zip(p_holdout, y_holdout)
                  if (p >= 0.5) == (yy == 1))
    acc = correct / len(p_holdout) if p_holdout else 0.0
    print(f'\nHoldout accuracy: {acc:.3f}')

    names = list(nm.LR_FEATURE_NAMES)
    ranked = sorted(zip(names, w), key=lambda x: -abs(x[1]))
    print('\nTop features by |coef|:')
    for nm_, wi in ranked[:12]:
        sign = '↑AI' if wi > 0 else '↓AI'
        print(f'  {nm_:<30} {wi:+.3f}  {sign}')

    output = {
        'version': '5.0.0-longform',
        'features': list(nm.LR_FEATURE_NAMES),
        'mean': means,
        'scale': scales,
        'coef': w,
        'intercept': b,
        'trained_on': (
            f'AI long-form (n={len(ai)}) + Human novel/news (n={len(hum)})'
        ),
        'n_train': len(X_train),
        'n_holdout': len(X_holdout),
        'holdout_accuracy': acc,
        'backend': 'sklearn',
    }
    with open(args.out, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f'\nSaved to {args.out}')


if __name__ == '__main__':
    main()
