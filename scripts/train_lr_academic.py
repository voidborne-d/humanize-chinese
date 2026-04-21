#!/usr/bin/env python3
"""Train academic-scene LR on Wikipedia academic + HC3 ChatGPT.

Difference from train_lr_scorer.py: human side is Wikipedia academic-register
text (formal, long-form, technical) instead of HC3 casual Q&A. AI side stays
HC3 ChatGPT. Resulting coefs better match the formal-academic register that
academic_cn humanize produces.
"""
import argparse
import json
import math
import os
import random
import re
import sys
from statistics import mean, stdev

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = '/Users/mac/claudeclaw/humanize'
HC3_PATH = f'{WORKSPACE}/data/hc3_chinese_all.jsonl'
WIKI_PATH = f'{WORKSPACE}/data/wiki_academic_corpus.txt'
DEFAULT_OUT = os.path.join(SCRIPT_DIR, 'lr_coef_academic.json')

sys.path.insert(0, SCRIPT_DIR)
import ngram_model as nm


def load_wiki_academic_chunks(path, chunk_min=200, chunk_size=500):
    """Naive sliding window over wiki corpus. Each chunk is ~chunk_size raw
    chars sliced from each entry. Returns list of strings with >= chunk_min CN chars."""
    raw = open(path, encoding='utf-8').read()
    entries = re.split(r'^=== .+? ===$', raw, flags=re.MULTILINE)
    chunks = []
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        # Slide non-overlapping window
        i = 0
        while i < len(entry):
            chunk = entry[i:i + chunk_size]
            if sum(1 for c in chunk if '\u4e00' <= c <= '\u9fff') >= chunk_min:
                chunks.append(chunk)
            i += chunk_size
    return chunks


def load_hc3_ai(path, n=500, seed=42, min_cn_chars=100):
    rng = random.Random(seed)
    texts = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            for a in row.get('chatgpt_answers', []) or []:
                if a and sum(1 for c in a if '\u4e00' <= c <= '\u9fff') >= min_cn_chars:
                    texts.append(a)
    rng.shuffle(texts)
    return texts[:n]


def standardize(X_train, X_holdout):
    n_feat = len(X_train[0])
    means = [mean(x[f] for x in X_train) for f in range(n_feat)]
    scales = [(stdev([x[f] for x in X_train]) or 1.0) for f in range(n_feat)]
    def s(x): return [(x[f] - means[f]) / scales[f] for f in range(n_feat)]
    return [s(x) for x in X_train], [s(x) for x in X_holdout], means, scales


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--n-ai', type=int, default=400)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--c', type=float, default=1.0)
    args = ap.parse_args()

    print(f'Loading academic chunks from {WIKI_PATH}...')
    academic_chunks = load_wiki_academic_chunks(WIKI_PATH)
    print(f'  Got {len(academic_chunks)} academic chunks')
    if len(academic_chunks) < 100:
        print('Warning: very few academic chunks, training may be unstable')

    print(f'Loading HC3 AI texts (n={args.n_ai})...')
    ai_texts = load_hc3_ai(HC3_PATH, n=args.n_ai, seed=args.seed)
    print(f'  Got {len(ai_texts)} AI texts')

    # Balance to min count
    n = min(len(academic_chunks), len(ai_texts))
    rng = random.Random(args.seed)
    rng.shuffle(academic_chunks)
    academic_chunks = academic_chunks[:n]
    ai_texts = ai_texts[:n]
    print(f'  Balanced to {n} per class')

    print(f'Extracting features...')
    X = []
    y = []
    for i, t in enumerate(ai_texts):
        vec, _ = nm.extract_feature_vector(t)
        X.append(vec)
        y.append(1)
        if (i + 1) % 50 == 0:
            print(f'  AI {i+1}/{n}')
    for i, t in enumerate(academic_chunks):
        vec, _ = nm.extract_feature_vector(t)
        X.append(vec)
        y.append(0)
        if (i + 1) % 50 == 0:
            print(f'  Academic {i+1}/{n}')

    # 80/20 split
    rng = random.Random(args.seed)
    idx_ai = list(range(n))
    idx_h = list(range(n, 2 * n))
    rng.shuffle(idx_ai); rng.shuffle(idx_h)
    split = int(0.8 * n)
    train_idx = idx_ai[:split] + idx_h[:split]
    holdout_idx = idx_ai[split:] + idx_h[split:]
    X_train = [X[i] for i in train_idx]
    y_train = [y[i] for i in train_idx]
    X_holdout = [X[i] for i in holdout_idx]
    y_holdout = [y[i] for i in holdout_idx]
    print(f'Train: {len(X_train)}  Holdout: {len(X_holdout)}')

    X_train_std, X_holdout_std, means, scales = standardize(X_train, X_holdout)

    try:
        from sklearn.linear_model import LogisticRegression
        lr = LogisticRegression(C=args.c, penalty='l2', solver='lbfgs', max_iter=1000)
        lr.fit(X_train_std, y_train)
        w = list(lr.coef_[0])
        b = float(lr.intercept_[0])
        backend = 'sklearn'
    except ImportError:
        print('sklearn not available; aborting (academic LR needs it for stability)')
        sys.exit(1)

    # Eval
    def predict(x):
        z = b + sum(x[i] * w[i] for i in range(len(w)))
        return 1.0 / (1.0 + math.exp(-z)) if z > -500 else 0.0
    p_holdout = [predict(x) for x in X_holdout_std]
    correct = sum(1 for p, yy in zip(p_holdout, y_holdout) if (p >= 0.5) == (yy == 1))
    acc = correct / len(p_holdout)
    print(f'\nHoldout accuracy: {acc:.3f}  (backend: {backend})')

    names = list(nm.LR_FEATURE_NAMES)
    ranked = sorted(zip(names, w), key=lambda x: -abs(x[1]))
    print(f'\nTop features by |coef| (standardized):')
    for nm_, wi in ranked:
        print(f'  {nm_:<30} {wi:+.3f}')

    ai_p = [p for p, yy in zip(p_holdout, y_holdout) if yy == 1]
    h_p = [p for p, yy in zip(p_holdout, y_holdout) if yy == 0]
    print(f'\nHoldout probs:')
    print(f'  AI       mean={mean(ai_p):.3f} median={sorted(ai_p)[len(ai_p)//2]:.3f}')
    print(f'  Academic mean={mean(h_p):.3f} median={sorted(h_p)[len(h_p)//2]:.3f}')

    # Save
    output = {
        'version': '3.4.0-academic',
        'features': list(nm.LR_FEATURE_NAMES),
        'mean': means,
        'scale': scales,
        'coef': w,
        'intercept': b,
        'trained_on': 'wiki_academic_corpus + hc3_chinese_all',
        'human_side': 'wikipedia_academic',
        'ai_side': 'hc3_chatgpt',
        'n_train': len(X_train),
        'n_holdout': len(X_holdout),
        'holdout_accuracy': acc,
        'backend': backend,
    }
    with open(args.out, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f'\nSaved to {args.out}')


if __name__ == '__main__':
    main()
