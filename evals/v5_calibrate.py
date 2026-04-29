#!/usr/bin/env python3
"""
v5 candidate signal calibration spike.

Goal: rank long-text / discourse-level signals NOT yet in detect_cn by
Cohen's d on AI vs Human longform samples. Use to pick top-3 for v5
implementation.

Signals span: paragraph-CV family, cross-paragraph cohesion (TF-IDF /
n-gram repeat / lexical chain), position-dependent perplexity, function
word distribution drift, sentence-starter diversity (3-char extension),
heading/list density. All zero-LLM, char-ngram statistical.

Usage:
  python evals/v5_calibrate.py --n 30
  python evals/v5_calibrate.py --n 50 --seed 7
"""

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
DATA = os.path.join(os.path.dirname(os.path.dirname(ROOT)), 'data')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

from ngram_model import _extract_chinese, compute_perplexity


def split_paragraphs(text, min_cn=20):
    raw = re.split(r'\n\s*\n', text)
    return [p.strip() for p in raw
            if p.strip() and len(_extract_chinese(p)) >= min_cn]


def split_sentences(para):
    parts = re.split(r'[。！？]', para)
    return [s.strip() for s in parts
            if s.strip() and len(_extract_chinese(s)) >= 5]


def _all_sentences(text):
    out = []
    for p in split_paragraphs(text):
        out.extend(split_sentences(p))
    return out


def _cv(values):
    if len(values) < 2:
        return None
    m = sum(values) / len(values)
    if m == 0:
        return None
    var = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(var) / m


# ─── Candidate signals (sign convention: positive d = AI > Human) ───

def sig_paragraph_length_cv(text):
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    return _cv([len(_extract_chinese(p)) for p in paras])


def sig_para_sent_count_cv(text):
    """CV of sentence-count per paragraph."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    counts = [len(split_sentences(p)) for p in paras]
    counts = [c for c in counts if c > 0]
    if len(counts) < 3:
        return None
    return _cv(counts)


def sig_cross_para_tfidf_cohesion(text, n=2):
    """Mean cosine sim between adjacent paragraphs using char-bigram TF-IDF.
    Higher = AI (tight topic), Lower = Human (drift)."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    para_tf = []
    for p in paras:
        chars = _extract_chinese(p)
        if len(chars) < n:
            continue
        grams = [''.join(chars[i:i+n]) for i in range(len(chars) - n + 1)]
        para_tf.append(Counter(grams))
    if len(para_tf) < 3:
        return None
    df = Counter()
    for tf in para_tf:
        for term in tf:
            df[term] += 1
    n_p = len(para_tf)
    idf = {term: math.log(n_p / df[term]) for term in df}
    para_vec = [{t: f * idf.get(t, 0) for t, f in tf.items()} for tf in para_tf]
    sims = []
    for i in range(n_p - 1):
        a, b = para_vec[i], para_vec[i+1]
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            continue
        sims.append(dot / (na * nb))
    return sum(sims) / len(sims) if sims else None


def sig_cross_para_3gram_repeat(text):
    """Fraction of char trigrams appearing in 2+ paragraphs.
    Higher = AI (repeat across paragraphs), Lower = Human (drift)."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    para_grams = []
    for p in paras:
        chars = _extract_chinese(p)
        grams = set(''.join(chars[i:i+3]) for i in range(len(chars) - 2))
        para_grams.append(grams)
    all_grams = set().union(*para_grams)
    if not all_grams:
        return None
    repeated = sum(1 for g in all_grams
                   if sum(1 for pg in para_grams if g in pg) >= 2)
    return repeated / len(all_grams)


def sig_3char_starter_diversity(text):
    """Unique 3-char openers / total sentences. Lower = AI repetitive."""
    sents = _all_sentences(text)
    if len(sents) < 5:
        return None
    starters = []
    for s in sents:
        chars = _extract_chinese(s)
        if len(chars) >= 3:
            starters.append(''.join(chars[:3]))
    if not starters:
        return None
    return len(set(starters)) / len(starters)


def sig_max_2char_starter_freq(text):
    """Max freq of any 2-char opener / total sentences. Higher = AI."""
    sents = _all_sentences(text)
    if len(sents) < 5:
        return None
    starters = Counter()
    for s in sents:
        chars = _extract_chinese(s)
        if len(chars) >= 2:
            starters[''.join(chars[:2])] += 1
    if not starters:
        return None
    return max(starters.values()) / len(sents)


def sig_function_word_kl_halves(text):
    """KL(half1 || half2) of top function word distribution.
    Higher = humans (drift), Lower = AI (uniform)."""
    chars = _extract_chinese(text)
    if len(chars) < 200:
        return None
    half = len(chars) // 2
    h1 = chars[:half]
    h2 = chars[half:]
    fws = ['的', '了', '是', '在', '和', '与', '及', '也',
           '都', '就', '但', '而', '或', '又', '所', '以']
    c1 = Counter(c for c in h1 if c in fws)
    c2 = Counter(c for c in h2 if c in fws)
    t1 = sum(c1.values()) or 1
    t2 = sum(c2.values()) or 1
    smooth = 0.5
    denom1 = t1 + smooth * len(fws)
    denom2 = t2 + smooth * len(fws)
    kl = 0.0
    for w in fws:
        p = (c1[w] + smooth) / denom1
        q = (c2[w] + smooth) / denom2
        kl += p * math.log(p / q)
    return kl


def sig_position_perplexity_first_vs_mid(text):
    """abs(perplexity_first_para - perplexity_mid_paras) / mid.
    Higher = humans (creative intro), Lower = AI (uniform)."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    first = paras[0]
    mid = ' '.join(paras[1:-1]) if len(paras) > 2 else paras[1]
    f_ppl = compute_perplexity(first).get('perplexity', 0)
    m_ppl = compute_perplexity(mid).get('perplexity', 0)
    if not m_ppl:
        return None
    return abs(f_ppl - m_ppl) / m_ppl


def sig_heading_list_density(text):
    """Per-line density of markdown headers / lists / numbering.
    Higher = AI (uses structure), Lower = Human."""
    lines = [l for l in text.split('\n') if l.strip()]
    if not lines:
        return None
    h = sum(1 for l in lines
            if re.match(r'^\s*(#{1,6}\s|[-*•]\s|\d+\.\s|（[一二三四五六七八九十]+）|[一二三四五六七八九十]+、)', l))
    return h / len(lines)


def sig_para_punct_density_cv(text):
    """CV of per-paragraph punctuation density. Lower = AI uniform."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    densities = []
    for p in paras:
        cn = len(_extract_chinese(p))
        if cn < 10:
            continue
        punct = len(re.findall(r'[，。、！？；：""''（）]', p))
        densities.append(punct / cn)
    if len(densities) < 3:
        return None
    return _cv(densities)


def sig_para_sent_len_cv_avg(text):
    """Mean of (sentence-length CV within each paragraph). Lower = AI uniform."""
    paras = split_paragraphs(text)
    if len(paras) < 3:
        return None
    cvs = []
    for p in paras:
        sents = split_sentences(p)
        if len(sents) < 3:
            continue
        sl = [len(_extract_chinese(s)) for s in sents]
        cv = _cv(sl)
        if cv is not None:
            cvs.append(cv)
    if len(cvs) < 2:
        return None
    return sum(cvs) / len(cvs)


SIGNALS = [
    ('paragraph_length_cv', sig_paragraph_length_cv, 'lower=AI'),
    ('para_sent_count_cv', sig_para_sent_count_cv, 'lower=AI'),
    ('cross_para_tfidf_cohesion', sig_cross_para_tfidf_cohesion, 'higher=AI'),
    ('cross_para_3gram_repeat', sig_cross_para_3gram_repeat, 'higher=AI'),
    ('3char_starter_diversity', sig_3char_starter_diversity, 'lower=AI'),
    ('max_2char_starter_freq', sig_max_2char_starter_freq, 'higher=AI'),
    ('function_word_kl_halves', sig_function_word_kl_halves, 'lower=AI'),
    ('position_ppl_first_vs_mid', sig_position_perplexity_first_vs_mid, 'lower=AI'),
    ('heading_list_density', sig_heading_list_density, 'higher=AI'),
    ('para_punct_density_cv', sig_para_punct_density_cv, 'lower=AI'),
    ('para_sent_len_cv_avg', sig_para_sent_len_cv_avg, 'lower=AI'),
]


def cohens_d(a, b):
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if len(a) < 5 or len(b) < 5:
        return None
    ma = sum(a) / len(a)
    mb = sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / len(a)
    vb = sum((x - mb) ** 2 for x in b) / len(b)
    pooled = math.sqrt((va + vb) / 2)
    if pooled == 0:
        return None
    return (ma - mb) / pooled


def _load_jsonl_texts(path, min_cn=500):
    items = []
    if not os.path.exists(path):
        return items
    with open(path) as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            text = o.get('text', '') or o.get('content', '')
            if len(_extract_chinese(text)) >= min_cn:
                items.append(text)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=30)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--min-cn', type=int, default=500)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    ai = _load_jsonl_texts(os.path.join(DATA, 'ai_longform_corpus.jsonl'),
                           min_cn=args.min_cn)
    human = []
    for p in ('human_novel_corpus.jsonl', 'human_news_corpus.jsonl'):
        human.extend(_load_jsonl_texts(os.path.join(DATA, p),
                                       min_cn=args.min_cn))

    rng.shuffle(ai)
    rng.shuffle(human)
    ai = ai[:args.n]
    human = human[:args.n]

    print(f'AI samples: {len(ai)}, Human samples: {len(human)} '
          f'(min_cn={args.min_cn})')
    print()
    print(f'{"signal":<32} {"polarity":<11} '
          f'{"AI mean":>10} {"Human mean":>12} {"d":>9} {"|d|":>6}')
    print('-' * 84)

    rows = []
    for name, fn, polarity in SIGNALS:
        ai_v = [fn(t) for t in ai]
        hu_v = [fn(t) for t in human]
        ai_c = [v for v in ai_v if v is not None]
        hu_c = [v for v in hu_v if v is not None]
        if not ai_c or not hu_c:
            print(f'{name:<32} {polarity:<11} {"N/A":>10} {"N/A":>12} '
                  f'{"N/A":>9} {"N/A":>6}')
            continue
        ma = sum(ai_c) / len(ai_c)
        mh = sum(hu_c) / len(hu_c)
        d = cohens_d(ai_c, hu_c)
        if d is None:
            d_str = 'N/A'
            ad = 0.0
        else:
            d_str = f'{d:+.3f}'
            ad = abs(d)
        rows.append((name, polarity, ma, mh, d, ad))
        print(f'{name:<32} {polarity:<11} {ma:>10.4f} {mh:>12.4f} '
              f'{d_str:>9} {ad:>6.3f}')

    print()
    print('Sorted by |d|:')
    rows.sort(key=lambda r: -r[5])
    for name, polarity, ma, mh, d, ad in rows:
        d_str = f'{d:+.3f}' if d is not None else 'N/A'
        marker = '★' if ad >= 1.0 else ('✓' if ad >= 0.5 else ' ')
        print(f'  {marker} {name:<32} d={d_str}  ({polarity})')


if __name__ == '__main__':
    main()
