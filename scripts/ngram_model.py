#!/usr/bin/env python3
"""
Chinese N-gram Language Model for AI Text Detection
Character-level bigram + trigram perplexity, burstiness, and entropy analysis.
Pure Python, no external dependencies.

Key insight: AI-generated Chinese text tends to have:
  - Lower perplexity (more predictable character sequences)
  - Lower burstiness (uniform complexity throughout)
  - More uniform entropy across paragraphs
"""

import json
import os
import re
from math import log2, exp

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FREQ_FILE = os.path.join(SCRIPT_DIR, 'ngram_freq_cn.json')

# ─── Frequency Table Loading ───

_FREQ_CACHE = None

def _load_freq():
    """Load n-gram frequency table (cached)."""
    global _FREQ_CACHE
    if _FREQ_CACHE is not None:
        return _FREQ_CACHE

    if not os.path.exists(FREQ_FILE):
        _FREQ_CACHE = {'unigrams': {}, 'bigrams': {}, 'trigrams': {},
                       'corpus_info': {'total_chars': 1}}
        return _FREQ_CACHE

    with open(FREQ_FILE, 'r', encoding='utf-8') as f:
        _FREQ_CACHE = json.load(f)

    # Convert string counts to int if needed
    for key in ('unigrams', 'bigrams', 'trigrams'):
        table = _FREQ_CACHE.get(key, {})
        _FREQ_CACHE[key] = {k: int(v) for k, v in table.items()}

    return _FREQ_CACHE


def _extract_chinese(text):
    """Extract only Chinese characters from text."""
    return re.findall(r'[\u4e00-\u9fff]', text)


# ─── Core Perplexity Computation ───

def _bigram_log_prob(c1, c2, freq):
    """
    Compute log2 probability of bigram (c1, c2) using add-k smoothing.
    P(c2|c1) ≈ (count(c1c2) + k) / (count(c1) + k * V)
    """
    unigrams = freq['unigrams']
    bigrams = freq['bigrams']
    V = max(len(unigrams), 1000)  # vocabulary size
    k = 0.01  # smoothing factor

    bigram_key = c1 + c2
    bi_count = bigrams.get(bigram_key, 0)
    uni_count = unigrams.get(c1, 0)

    prob = (bi_count + k) / (uni_count + k * V)
    return log2(prob) if prob > 0 else -20.0  # floor for unseen


def _trigram_log_prob(c1, c2, c3, freq):
    """
    Compute log2 probability of trigram using interpolation with bigrams.
    P_interp = lambda * P_tri(c3|c1c2) + (1-lambda) * P_bi(c3|c2)
    """
    bigrams = freq['bigrams']
    trigrams = freq['trigrams']
    V = max(len(freq['unigrams']), 1000)
    k = 0.01
    lam = 0.6  # trigram weight

    # Trigram probability
    tri_key = c1 + c2 + c3
    bi_context_key = c1 + c2
    tri_count = trigrams.get(tri_key, 0)
    bi_context_count = bigrams.get(bi_context_key, 0)
    p_tri = (tri_count + k) / (bi_context_count + k * V)

    # Bigram probability (backoff)
    p_bi_raw = _bigram_log_prob(c2, c3, freq)
    p_bi = 2 ** p_bi_raw  # convert back from log2

    # Interpolation in probability space
    p_interp = lam * p_tri + (1 - lam) * p_bi
    return log2(p_interp) if p_interp > 0 else -20.0


def compute_unigram_perplexity(text):
    """Character unigram perplexity. AI Chinese tends to concentrate more on
    common characters (lower uni ppl) than human writing.

    Returns float or 0.0 if text too short.
    """
    freq = _load_freq()
    chars = _extract_chinese(text)
    if len(chars) < 5:
        return 0.0
    unigrams = freq['unigrams']
    total = sum(unigrams.values()) or 1
    V = max(len(unigrams), 1000)
    k = 0.01
    avg_lp = 0.0
    for c in chars:
        count = unigrams.get(c, 0)
        prob = (count + k) / (total + k * V)
        avg_lp += log2(prob) if prob > 0 else -20.0
    avg_lp /= len(chars)
    return 2 ** (-avg_lp)


def compute_perplexity(text, window_size=0):
    """
    Compute character-level perplexity of Chinese text using interpolated trigram model.

    Args:
        text: input text string
        window_size: if > 0, compute per-window perplexities for burstiness.
                     0 means compute whole-text perplexity only.

    Returns:
        dict with:
          - perplexity: overall perplexity (float)
          - avg_log_prob: average log2 probability per character
          - window_perplexities: list of per-window perplexities (if window_size > 0)
          - log_probs: per-character log prob series (used for DivEye surprisal stats)
          - char_count: number of Chinese characters used
    """
    freq = _load_freq()
    chars = _extract_chinese(text)

    if len(chars) < 5:
        return {
            'perplexity': 0.0,
            'avg_log_prob': 0.0,
            'window_perplexities': [],
            'log_probs': [],
            'char_count': len(chars),
        }

    # Compute per-character log probabilities using trigram model
    log_probs = []
    for i in range(2, len(chars)):
        lp = _trigram_log_prob(chars[i-2], chars[i-1], chars[i], freq)
        log_probs.append(lp)

    if not log_probs:
        return {
            'perplexity': 0.0,
            'avg_log_prob': 0.0,
            'window_perplexities': [],
            'log_probs': [],
            'char_count': len(chars),
        }

    # Overall perplexity: 2^(-avg_log_prob)
    avg_lp = sum(log_probs) / len(log_probs)
    perplexity = 2 ** (-avg_lp)

    # Per-window perplexities
    window_ppls = []
    if window_size > 0 and len(log_probs) >= window_size:
        for start in range(0, len(log_probs) - window_size + 1, window_size // 2):
            end = min(start + window_size, len(log_probs))
            chunk = log_probs[start:end]
            if chunk:
                w_avg = sum(chunk) / len(chunk)
                window_ppls.append(2 ** (-w_avg))

    return {
        'perplexity': perplexity,
        'avg_log_prob': avg_lp,
        'window_perplexities': window_ppls,
        'log_probs': log_probs,
        'char_count': len(chars),
    }


# ─── DivEye-style surprisal serialization features ───
#
# Based on Basani & Chen, TMLR 2026 ("Diversity Boosts AI-Generated Text Detection"):
# human text has structured irregularity in its surprisal series — autocorrelation
# signals (local repetition of predictable/unpredictable runs) and spectral
# flatness (how "white-noise-y" the surprisal series is).
#
# Intuition in Chinese:
#   - Human writing alternates bursts of common characters (low surprisal)
#     with rare/creative choices (high surprisal) → non-uniform spectrum.
#   - LLM writing is smoother — moderate surprisal everywhere → flat spectrum
#     close to white noise (high flatness).

def _autocorrelation(series, lag):
    """Pearson autocorrelation of a numeric series at a given lag.
    Returns 0.0 if series too short or variance zero."""
    n = len(series)
    if n <= lag + 2:
        return 0.0
    mean = sum(series) / n
    num = 0.0
    den = 0.0
    for i in range(n):
        d = series[i] - mean
        den += d * d
        if i >= lag:
            num += d * (series[i - lag] - mean)
    if den <= 0:
        return 0.0
    return num / den


def _spectral_flatness(series):
    """
    Spectral flatness = geometric_mean(|DFT|^2) / arithmetic_mean(|DFT|^2).
    Range [0, 1]. 1.0 = perfectly white/flat spectrum (AI-like).
    Lower = more structured (human-like).

    Pure-Python DFT via naive O(N²). OK for N < 500 chars; sample if larger.
    """
    n = len(series)
    if n < 16:
        return 0.0

    # Subsample if too long (keeps computation under ~20ms for 500-char text)
    max_n = 256
    if n > max_n:
        step = n / max_n
        series = [series[int(i * step)] for i in range(max_n)]
        n = max_n

    # De-mean
    mean = sum(series) / n
    x = [v - mean for v in series]

    # Compute magnitude-squared of DFT for k = 1..n/2 (skip DC)
    # Using cos/sin table for speed
    from math import cos, sin, pi, log, exp
    power = []
    half = n // 2
    for k in range(1, half):
        re = 0.0
        im = 0.0
        for t, val in enumerate(x):
            angle = -2.0 * pi * k * t / n
            re += val * cos(angle)
            im += val * sin(angle)
        p = re * re + im * im
        # Floor to avoid log(0)
        power.append(max(p, 1e-12))

    if not power:
        return 0.0

    # Geometric mean via log-arith
    log_sum = sum(log(p) for p in power)
    geo = exp(log_sum / len(power))
    arith = sum(power) / len(power)
    if arith <= 0:
        return 0.0
    return geo / arith


def _distribution_moments(series):
    """Skewness and excess kurtosis of series. Returns (skew, kurt) or (0, 0)."""
    n = len(series)
    if n < 4:
        return 0.0, 0.0
    mean = sum(series) / n
    var = sum((v - mean) ** 2 for v in series) / n
    if var <= 0:
        return 0.0, 0.0
    std = var ** 0.5
    skew = sum(((v - mean) / std) ** 3 for v in series) / n
    kurt = sum(((v - mean) / std) ** 4 for v in series) / n - 3.0
    return skew, kurt


def compute_gltr_buckets(text):
    """
    GLTR-style (Gehrmann ACL 2019) rank-bucket distribution.

    For each bigram position (c_{i-1}, c_i) in the text, we look at the ranked
    list of characters that most often follow c_{i-1} in our corpus, and count
    which bucket the observed c_i falls into:
      - top10: c_i is among the 10 most likely followers of c_{i-1}
      - top100: top 11-100
      - top1000: top 101-1000
      - beyond: rank > 1000 or bigram unseen

    AI text tends to favor high-probability continuations (top10-heavy),
    human text has more "beyond" choices.

    Returns dict with bucket counts, proportions, and a crude "ai_score" from
    the top10 proportion.
    """
    freq = _load_freq()
    bigrams = freq.get('bigrams', {})
    if not bigrams:
        return {}

    chars = _extract_chinese(text)
    if len(chars) < 30:
        return {}

    # Precompute ranked followers for each prefix char we see in text
    # (only compute for prefixes present in text — saves work)
    prefixes_needed = set(chars[:-1])

    ranked_by_prefix = {}
    for bg, cnt in bigrams.items():
        if len(bg) != 2:
            continue
        prefix = bg[0]
        if prefix not in prefixes_needed:
            continue
        ranked_by_prefix.setdefault(prefix, []).append((bg[1], cnt))
    for prefix in ranked_by_prefix:
        ranked_by_prefix[prefix].sort(key=lambda x: -x[1])

    buckets = {'top10': 0, 'top100': 0, 'top1000': 0, 'beyond': 0}

    for i in range(1, len(chars)):
        prev = chars[i - 1]
        curr = chars[i]
        ranked = ranked_by_prefix.get(prev)
        if not ranked:
            buckets['beyond'] += 1
            continue
        # Find rank of curr
        rank = None
        for j, (ch, _) in enumerate(ranked):
            if ch == curr:
                rank = j
                break
        if rank is None:
            buckets['beyond'] += 1
        elif rank < 10:
            buckets['top10'] += 1
        elif rank < 100:
            buckets['top100'] += 1
        elif rank < 1000:
            buckets['top1000'] += 1
        else:
            buckets['beyond'] += 1

    total = sum(buckets.values())
    if total == 0:
        return {}
    proportions = {k: v / total for k, v in buckets.items()}
    return {
        'counts': buckets,
        'proportions': proportions,
        'total': total,
    }


def compute_diveye_features(log_probs):
    """
    Compute DivEye-style features from a per-character log-prob series.

    Returns dict with:
      - autocorr_lag1 / lag2 / lag4 / lag8: lagged autocorrelations
        (human text typically has higher short-lag autocorrelation)
      - spectral_flatness: [0, 1], higher = flatter = AI-like
      - skew, excess_kurt: distribution shape
    """
    if len(log_probs) < 16:
        return {
            'autocorr_lag1': 0.0,
            'autocorr_lag2': 0.0,
            'autocorr_lag4': 0.0,
            'autocorr_lag8': 0.0,
            'spectral_flatness': 0.0,
            'skew': 0.0,
            'excess_kurt': 0.0,
        }
    skew, kurt = _distribution_moments(log_probs)
    return {
        'autocorr_lag1': _autocorrelation(log_probs, 1),
        'autocorr_lag2': _autocorrelation(log_probs, 2),
        'autocorr_lag4': _autocorrelation(log_probs, 4),
        'autocorr_lag8': _autocorrelation(log_probs, 8),
        'spectral_flatness': _spectral_flatness(log_probs),
        'skew': skew,
        'excess_kurt': kurt,
    }


# ─── DetectGPT-lite curvature (paper research 2026-04-19 cycle 10) ───
#
# For each char position, compute log-prob of actual char minus mean log-prob
# of top-K alternative chars (from global unigram freq). High curvature =
# original char much more probable than alternatives = AI (greedy decode).
# Low curvature = original is one of many plausible choices = human (creative).
#
# HC3 200+200 calibration: AI mean curvature 0.673 vs human 0.348, Cohen's d = 0.77.
# Threshold 0.6 flags 55% AI vs 26% human (spread 29%).
# Inspired by Fast-DetectGPT (Bao et al. ICLR 2024, arxiv 2310.05130) but replaces
# the LLM masked-sampling with a lightweight trigram-table alternative lookup.

# Top-500 most common Chinese chars — cached on first call
_TOP_CHARS_CACHE = None

def _top_chars(k=500):
    global _TOP_CHARS_CACHE
    if _TOP_CHARS_CACHE is None:
        freq = _load_freq()
        _TOP_CHARS_CACHE = [c for c, _ in sorted(
            freq['unigrams'].items(), key=lambda x: -x[1]
        )[:k]]
    return _TOP_CHARS_CACHE


def compute_curvature(text, n_positions=50, k_alts=10, seed=42):
    """Mean log-prob curvature over sampled positions.

    Returns dict with:
      curvature_mean: mean of (log_p(actual) - mean log_p(top-K alternatives))
      n_positions: number of positions evaluated
    """
    chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    if len(chars) < 30:
        return {'curvature_mean': 0.0, 'n_positions': 0}

    freq = _load_freq()
    top = _top_chars()
    import random as _random
    rng = _random.Random(seed)
    positions = list(range(2, len(chars)))
    if len(positions) > n_positions:
        positions = rng.sample(positions, n_positions)

    curvs = []
    for i in positions:
        c1, c2, actual = chars[i-2], chars[i-1], chars[i]
        actual_lp = _trigram_log_prob(c1, c2, actual, freq)
        alt_lps = []
        for alt in top:
            if alt == actual: continue
            alt_lps.append(_trigram_log_prob(c1, c2, alt, freq))
            if len(alt_lps) >= k_alts:
                break
        if alt_lps:
            curvs.append(actual_lp - sum(alt_lps) / len(alt_lps))

    if not curvs:
        return {'curvature_mean': 0.0, 'n_positions': 0}
    return {'curvature_mean': sum(curvs) / len(curvs), 'n_positions': len(curvs)}


# ─── Binoculars dual ngram ratio (B-path 2026-04-19 cycle 23) ───
#
# Inspired by Binoculars (Hans et al. ICML 2024, arxiv 2401.12070) and
# GramGuard (OpenReview 2025 oOf83pSxUP). Trains a secondary char-level trigram
# on HC3 human_answers (2.3M chars, 80/20 train/holdout split seed=42) and
# computes log-prob divergence vs the primary ngram.
#
# Intuition:
#   - AI text: trained to produce "average" Chinese → equally predictable under
#     both ngrams → log-prob ratio close to 1.
#   - Human text: has idiosyncratic distributional features → ngrams disagree
#     → ratio diverges from 1.
#
# Secondary ngram file: scripts/ngram_freq_cn_human.json (20MB, .gitignored,
# regenerate via `python scripts/train_ngram_human.py`)

_HUMAN_FREQ_CACHE = None
_HUMAN_FREQ_FILE = os.path.join(SCRIPT_DIR, 'ngram_freq_cn_human.json')


def _load_human_freq():
    """Lazy-load the secondary (human-biased) ngram frequency table.
    Returns None if file missing (B-2 not run yet)."""
    global _HUMAN_FREQ_CACHE
    if _HUMAN_FREQ_CACHE is not None:
        return _HUMAN_FREQ_CACHE
    if not os.path.exists(_HUMAN_FREQ_FILE):
        _HUMAN_FREQ_CACHE = None
        return None
    with open(_HUMAN_FREQ_FILE, 'r', encoding='utf-8') as f:
        _HUMAN_FREQ_CACHE = json.load(f)
    for key in ('unigrams', 'bigrams', 'trigrams'):
        table = _HUMAN_FREQ_CACHE.get(key, {})
        _HUMAN_FREQ_CACHE[key] = {k: int(v) for k, v in table.items()}
    return _HUMAN_FREQ_CACHE


_WIKI_FREQ_CACHE = None
_WIKI_FREQ_FILE = os.path.join(SCRIPT_DIR, 'ngram_freq_cn_wiki.json')


def _load_wiki_freq():
    """Lazy-load Wikipedia ngram frequency table (F-3, 2026-04-22).
    Returns None if file missing — graceful fallback when feature is disabled."""
    global _WIKI_FREQ_CACHE
    if _WIKI_FREQ_CACHE is not None:
        return _WIKI_FREQ_CACHE
    if not os.path.exists(_WIKI_FREQ_FILE):
        _WIKI_FREQ_CACHE = None
        return None
    with open(_WIKI_FREQ_FILE, 'r', encoding='utf-8') as f:
        _WIKI_FREQ_CACHE = json.load(f)
    for key in ('unigrams', 'bigrams', 'trigrams'):
        table = _WIKI_FREQ_CACHE.get(key, {})
        _WIKI_FREQ_CACHE[key] = {k: int(v) for k, v in table.items()}
    return _WIKI_FREQ_CACHE


_NEWS_FREQ_CACHE = None
_NEWS_FREQ_FILE = os.path.join(SCRIPT_DIR, 'ngram_freq_cn_news.json')


def _load_news_freq():
    """Lazy-load news ngram (THUCNews-derived). Returns None if missing."""
    global _NEWS_FREQ_CACHE
    if _NEWS_FREQ_CACHE is not None:
        return _NEWS_FREQ_CACHE
    if not os.path.exists(_NEWS_FREQ_FILE):
        _NEWS_FREQ_CACHE = None
        return None
    with open(_NEWS_FREQ_FILE, 'r', encoding='utf-8') as f:
        _NEWS_FREQ_CACHE = json.load(f)
    for key in ('unigrams', 'bigrams', 'trigrams'):
        table = _NEWS_FREQ_CACHE.get(key, {})
        _NEWS_FREQ_CACHE[key] = {k: int(v) for k, v in table.items()}
    return _NEWS_FREQ_CACHE


def compute_news_lp_diff(text):
    """News-vs-{human, wiki} log-prob divergences.

    HC3 300+300 Cohen's d on expanded 10-category news corpus:
    news_vs_human=1.20, news_vs_wiki=0.27. AI text is much closer
    to news register than casual human Q&A answers are.
    """
    news = _load_news_freq()
    human = _load_human_freq()
    wiki = _load_wiki_freq()
    if news is None or human is None or wiki is None:
        return {'available': False, 'news_vs_human': 0.0, 'news_vs_wiki': 0.0}

    chars = _extract_chinese(text)
    if len(chars) < 30:
        return {'available': True, 'news_vs_human': 0.0, 'news_vs_wiki': 0.0}

    n_sum = h_sum = w_sum = 0.0
    n = 0
    for i in range(2, len(chars)):
        n_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], news)
        h_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], human)
        w_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], wiki)
        n += 1
    if n == 0:
        return {'available': True, 'news_vs_human': 0.0, 'news_vs_wiki': 0.0}
    n_avg = n_sum / n
    h_avg = h_sum / n
    w_avg = w_sum / n
    return {
        'available': True,
        'news_vs_human': n_avg - h_avg,
        'news_vs_wiki': n_avg - w_avg,
    }


def compute_wiki_lp_diff(text):
    """Compute Wikipedia-corpus log-prob divergences for Binoculars-style signal.

    Returns:
      wiki_vs_human: mean(lp_wiki) - mean(lp_human)
      wiki_vs_primary: mean(lp_primary) - mean(lp_wiki)

    HC3 300+300 pilot Cohen's d:
      wiki_vs_human  = 1.58 (strongest seen)
      wiki_vs_primary = 1.13

    Interpretation: AI text sits closer to encyclopedic Wikipedia distribution
    than casual human Q&A does, providing an orthogonal signal to bino_lp_diff.
    """
    wiki_freq = _load_wiki_freq()
    human_freq = _load_human_freq()
    primary_freq = _load_freq()
    if wiki_freq is None or human_freq is None:
        return {'available': False, 'char_count': 0,
                'wiki_vs_human': 0.0, 'wiki_vs_primary': 0.0}

    chars = _extract_chinese(text)
    if len(chars) < 30:
        return {'available': True, 'char_count': len(chars),
                'wiki_vs_human': 0.0, 'wiki_vs_primary': 0.0}

    p_sum = w_sum = h_sum = 0.0
    n = 0
    for i in range(2, len(chars)):
        p_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], primary_freq)
        w_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], wiki_freq)
        h_sum += _trigram_log_prob(chars[i-2], chars[i-1], chars[i], human_freq)
        n += 1
    if n == 0:
        return {'available': True, 'char_count': len(chars),
                'wiki_vs_human': 0.0, 'wiki_vs_primary': 0.0}

    p_avg = p_sum / n
    w_avg = w_sum / n
    h_avg = h_sum / n
    return {
        'available': True,
        'char_count': len(chars),
        'wiki_vs_human': w_avg - h_avg,
        'wiki_vs_primary': p_avg - w_avg,
    }


def compute_binoculars_ratio(text):
    """Compute Binoculars-style log-prob divergence between primary and human ngrams.

    Returns dict with:
      available: True if secondary ngram loaded, False if missing
      mean_lp_diff: mean of (lp_primary - lp_human) per char
      std_lp_diff: std of lp difference
      abs_mean_lp_diff: abs(mean_lp_diff) — how far the two ngrams disagree
      ppl_ratio: 2 ^ mean_lp_diff (ratio of secondary ppl to primary ppl)
      char_count: chars evaluated
    """
    human_freq = _load_human_freq()
    primary_freq = _load_freq()
    if human_freq is None:
        return {'available': False, 'char_count': 0}

    chars = _extract_chinese(text)
    if len(chars) < 30:
        return {'available': True, 'char_count': len(chars),
                'mean_lp_diff': 0.0, 'std_lp_diff': 0.0,
                'abs_mean_lp_diff': 0.0, 'ppl_ratio': 1.0}

    diffs = []
    for i in range(2, len(chars)):
        lp_primary = _trigram_log_prob(chars[i-2], chars[i-1], chars[i], primary_freq)
        lp_human = _trigram_log_prob(chars[i-2], chars[i-1], chars[i], human_freq)
        diffs.append(lp_primary - lp_human)

    n = len(diffs)
    mean_d = sum(diffs) / n
    var_d = sum((x - mean_d) ** 2 for x in diffs) / n
    std_d = var_d ** 0.5
    ppl_ratio = 2 ** mean_d

    return {
        'available': True,
        'char_count': len(chars),
        'mean_lp_diff': mean_d,
        'std_lp_diff': std_d,
        'abs_mean_lp_diff': abs(mean_d),
        'ppl_ratio': ppl_ratio,
    }


# ─── Transition-word density (CNKI 语义逻辑链, HC3 2026-04-19) ───
#
# Paper research (memory/research_chinese_aigc_papers_2026-04-19.md Part 1)
# identified CNKI's 语义逻辑链 as relying on transition/logic markers. On
# HC3-Chinese 300+300 calibration we find ChatGPT uses ~2× more transition
# phrases than humans (mean 13.7 vs 6.98 per 1000 Chinese chars, Cohen's d = 0.617).
#
# NOTE on direction: our earlier hypothesis ("humans use transitions to signal
# thinking") turned out to be the opposite on HC3 Q&A corpus. ChatGPT overuses
# formal connectors (然而/此外/综上所述/首先/值得注意的是) because it mimics
# textbook style. Humans write more casual Q&A with zero-inflated transition use
# (median 0 per 1000 chars).

_TRANSITION_PHRASES = [
    # Structural / ordering
    '首先', '其次', '再次', '最后', '然后', '接下来', '与此同时',
    # Summary / conclusion
    '综上所述', '总的来说', '总而言之', '归根结底', '由此可见',
    '一方面', '另一方面', '换言之', '简而言之',
    # Spotlight / emphasis
    '值得注意的是', '需要指出的是', '需要强调的是', '不可否认',
    '尤其是', '特别是', '尤为', '显著',
    # Contrast / concession
    '然而', '不过', '相反', '相较而言', '与之相对', '反之', '反观',
    '诚然', '固然', '纵然', '尽管如此',
    # Causation / consequence
    '因此', '所以', '故而', '由此', '进而', '从而', '基于此',
    # Elaboration
    '此外', '另外', '除此之外', '具体而言', '具体来说', '具体地说',
    '举例来说', '举个例子', '更进一步', '进一步',
    '事实上', '实际上', '实质上', '本质上',
    # Hedging — ChatGPT overuses
    '或许', '不妨', '也许', '大致', '大概', '某种程度上', '一定程度上',
    '可能', '应当', '应该', '理论上',
    '需要注意', '需要说明', '值得一提', '请注意',
]


def compute_transition_density(text):
    """Count occurrences of ChatGPT-style transition phrases per 1000 Chinese chars.

    Uses substring match (no tokenization needed). ChatGPT on HC3 averages 13.7
    per 1000 chars vs 6.98 for humans (d = 0.617).
    """
    cn = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if cn < 50:
        return {'count': 0, 'density': 0.0, 'cn_chars': cn}
    count = sum(text.count(w) for w in _TRANSITION_PHRASES)
    return {'count': count, 'density': count / cn * 1000, 'cn_chars': cn}


# ─── Punctuation density (HC3 calibration 2026-04-19) ───
#
# HC3-Chinese finding: humans use MORE punctuation than ChatGPT (opposite of
# AIMS 2025 claim for academic domain). On HC3 Q&A data:
#   comma density per 100 non-whitespace chars:
#     human mean 4.82, AI mean 3.82, Cohen's d = -0.47
# We flag low_comma_density (< 4.5 per 100 chars) as AI indicator.
# Reason for direction difference vs AIMS paper: HC3 humans are casual Q&A
# writers (lots of 啊/吧/吗 with commas), ChatGPT writes cleaner flowing prose
# with longer uninterrupted clauses.

def compute_punctuation_density(text):
    """Comma density and total punctuation density per 100 non-ws chars.

    Returns dict with:
      total_chars: non-whitespace character count
      comma_count: number of full/half-width commas
      punct_count: number of any Chinese/ASCII punctuation
      comma_density: commas per 100 non-ws chars
      punct_density: total punctuation per 100 non-ws chars
    """
    chars = [c for c in text if c.strip()]
    n = len(chars)
    if n == 0:
        return {'total_chars': 0, 'comma_count': 0, 'punct_count': 0,
                'comma_density': 0.0, 'punct_density': 0.0}
    commas = sum(1 for c in chars if c in '，,')
    puncts = sum(1 for c in chars if c in '，。、；：！？（）「」『』“”‘’"\'.,:;!?()[]{}《》—…·')
    return {
        'total_chars': n, 'comma_count': commas, 'punct_count': puncts,
        'comma_density': commas / n * 100,
        'punct_density': puncts / n * 100,
    }


# ─── Sentence length burstiness (paper research 2026-04-19) ───
#
# AI Chinese text: 15-25 char sentences with low CV. Human: mixed short/long, CV 0.5-0.7.
# Source: AIMS 2025 "Chinese deep learning AIGC detection" + CNKI 三链路 "语言模式链"
#
# We separate this from char-level burstiness (compute_burstiness above, which is
# perplexity-CV within 50-char windows). Sentence-length burstiness is a structural
# signal — the rhythm between sentence boundaries.

def compute_sentence_length_features(text):
    """Statistical features of sentence-length distribution.

    Returns:
      n_sentences: sentences of >= 3 Chinese chars
      mean_len:    mean Chinese chars per sentence
      std_len:     population stddev
      cv:          coefficient of variation (std/mean)
      short_frac:  fraction of sentences with < 10 Chinese chars
      long_frac:   fraction of sentences with > 30 Chinese chars
      equal_mid_frac: fraction in the 15-25 "AI equal-length" band
    """
    parts = re.split(r'[。！？\n]', text)
    lengths = []
    for p in parts:
        cn = sum(1 for c in p if '\u4e00' <= c <= '\u9fff')
        if cn >= 3:
            lengths.append(cn)

    n = len(lengths)
    if n < 3:
        return {
            'n_sentences': n, 'mean_len': 0.0, 'std_len': 0.0, 'cv': 0.0,
            'short_frac': 0.0, 'long_frac': 0.0, 'equal_mid_frac': 0.0,
        }

    mean_len = sum(lengths) / n
    if mean_len == 0:
        return {
            'n_sentences': n, 'mean_len': 0.0, 'std_len': 0.0, 'cv': 0.0,
            'short_frac': 0.0, 'long_frac': 0.0, 'equal_mid_frac': 0.0,
        }

    variance = sum((x - mean_len) ** 2 for x in lengths) / n
    std_len = variance ** 0.5
    cv = std_len / mean_len
    short_frac = sum(1 for x in lengths if x < 10) / n
    long_frac = sum(1 for x in lengths if x > 30) / n
    equal_mid_frac = sum(1 for x in lengths if 15 <= x <= 25) / n

    return {
        'n_sentences': n, 'mean_len': mean_len, 'std_len': std_len,
        'cv': cv, 'short_frac': short_frac, 'long_frac': long_frac,
        'equal_mid_frac': equal_mid_frac,
    }


# ─── MATTR / lexical diversity (E-8 / PATTR-lite per arxiv 2507.15092) ───
#
# HC3 300+300 calibration: char_mattr(window=100) Cohen's d = 0.700 (AI mean
# 0.6274, human mean 0.6805). AI text uses a narrower character repertoire
# per 100-char window — human Chinese writing varies vocabulary more.
# Measured directly from Chinese chars only (skip ascii / punct / digits).

def compute_char_mattr(text, window=100):
    """Moving-Average Type-Token Ratio over Chinese chars.

    Windows of `window` chars with 50% overlap; return mean of
    (unique_chars / window) across windows.

    Returns 0.0 for texts shorter than one window (caller should gate).
    """
    chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    if len(chars) < window:
        return 0.0
    step = max(1, window // 2)
    ratios = []
    for i in range(0, len(chars) - window + 1, step):
        seg = chars[i:i + window]
        ratios.append(len(set(seg)) / len(seg))
    return sum(ratios) / len(ratios) if ratios else 0.0


# ─── Burstiness ───

def compute_burstiness(text, window_size=50):
    """
    Compute burstiness as coefficient of variation of windowed perplexities.

    Human text: higher burstiness (CV > 0.3, some parts simple, some complex)
    AI text: lower burstiness (CV < 0.2, uniformly smooth)

    Args:
        text: input text
        window_size: character window for perplexity segments

    Returns:
        dict with:
          - burstiness: coefficient of variation (std/mean) of window perplexities
          - mean_ppl: mean of window perplexities
          - std_ppl: standard deviation of window perplexities
          - n_windows: number of windows analyzed
    """
    result = compute_perplexity(text, window_size=window_size)
    ppls = result['window_perplexities']

    if len(ppls) < 3:
        return {
            'burstiness': 0.0,
            'mean_ppl': result['perplexity'],
            'std_ppl': 0.0,
            'n_windows': len(ppls),
        }

    mean_ppl = sum(ppls) / len(ppls)
    if mean_ppl == 0:
        return {
            'burstiness': 0.0,
            'mean_ppl': 0.0,
            'std_ppl': 0.0,
            'n_windows': len(ppls),
        }

    variance = sum((p - mean_ppl) ** 2 for p in ppls) / len(ppls)
    std_ppl = variance ** 0.5
    cv = std_ppl / mean_ppl

    return {
        'burstiness': cv,
        'mean_ppl': mean_ppl,
        'std_ppl': std_ppl,
        'n_windows': len(ppls),
    }


# ─── Paragraph Entropy Uniformity ───

def compute_entropy_uniformity(text):
    """
    Compute entropy of each paragraph and measure how uniform they are.

    AI text: paragraphs have very similar entropy (low CV)
    Human text: entropy varies more between paragraphs

    Returns:
        dict with:
          - entropy_cv: coefficient of variation of per-paragraph entropy
          - paragraph_entropies: list of (paragraph_index, entropy) tuples
          - mean_entropy: mean paragraph entropy
          - n_paragraphs: number of paragraphs analyzed
    """
    # Split into paragraphs (by double newline or single newline with enough content)
    raw_paras = re.split(r'\n\s*\n|\n', text)
    paragraphs = [p.strip() for p in raw_paras
                  if p.strip() and len(_extract_chinese(p.strip())) >= 20]

    if len(paragraphs) < 3:
        return {
            'entropy_cv': 0.0,
            'paragraph_entropies': [],
            'mean_entropy': 0.0,
            'n_paragraphs': len(paragraphs),
        }

    # Compute per-paragraph bigram entropy
    para_entropies = []
    for i, para in enumerate(paragraphs):
        chars = _extract_chinese(para)
        if len(chars) < 10:
            continue

        # Bigram frequency within paragraph
        bigrams = {}
        for j in range(len(chars) - 1):
            key = chars[j] + chars[j+1]
            bigrams[key] = bigrams.get(key, 0) + 1

        total = sum(bigrams.values())
        if total == 0:
            continue

        entropy = 0.0
        for count in bigrams.values():
            p = count / total
            if p > 0:
                entropy -= p * log2(p)

        para_entropies.append((i, entropy))

    if len(para_entropies) < 3:
        return {
            'entropy_cv': 0.0,
            'paragraph_entropies': para_entropies,
            'mean_entropy': 0.0,
            'n_paragraphs': len(para_entropies),
        }

    entropies = [e for _, e in para_entropies]
    mean_ent = sum(entropies) / len(entropies)

    if mean_ent == 0:
        return {
            'entropy_cv': 0.0,
            'paragraph_entropies': para_entropies,
            'mean_entropy': 0.0,
            'n_paragraphs': len(para_entropies),
        }

    variance = sum((e - mean_ent) ** 2 for e in entropies) / len(entropies)
    std_ent = variance ** 0.5
    cv = std_ent / mean_ent

    return {
        'entropy_cv': cv,
        'paragraph_entropies': para_entropies,
        'mean_entropy': mean_ent,
        'n_paragraphs': len(para_entropies),
    }


def compute_paragraph_length_cv(text):
    """
    Coefficient of variation of paragraph lengths (Chinese-char count).

    AI long-form text writes paragraphs of similar length; human
    long-form alternates short and long paragraphs.

    v5 calibration n=50 longform vs novel/news (2026-04-29):
      AI mean 0.359, Human mean 0.742, Cohen's d = -1.49

    Already used as a binary rule trigger in detect_cn at threshold 0.2
    via inline computation (uniform_paragraphs). This function exposes
    the same value as a continuous LR feature so the signal propagates
    through fusion even on samples whose CV stays just above the
    binary threshold.

    Returns:
        dict with:
          - cv: paragraph length CV
          - n_paragraphs: paragraphs counted (>=20 cn chars)
          - mean_length: mean paragraph length (cn chars)
    """
    raw = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in raw
                  if p.strip() and len(_extract_chinese(p.strip())) >= 20]

    if len(paragraphs) < 3:
        return {
            'cv': 0.0,
            'n_paragraphs': len(paragraphs),
            'mean_length': 0.0,
        }

    lens = [len(_extract_chinese(p)) for p in paragraphs]
    m = sum(lens) / len(lens)
    if m == 0:
        return {
            'cv': 0.0,
            'n_paragraphs': len(paragraphs),
            'mean_length': 0.0,
        }
    var = sum((l - m) ** 2 for l in lens) / len(lens)
    return {
        'cv': (var ** 0.5) / m,
        'n_paragraphs': len(paragraphs),
        'mean_length': m,
    }


def compute_para_sent_len_cv(text):
    """
    Mean of per-paragraph sentence-length CV.

    For each paragraph (>=3 sentences), compute the coefficient of variation
    of Chinese-character sentence lengths within that paragraph. Take the
    mean across paragraphs.

    AI text: paragraph-internal sentences are uniform in length (low avg CV)
    Human text: paragraph-internal sentences vary (high avg CV)

    v5 calibration n=50 longform AI vs novel/news Human (2026-04-29):
      AI mean 0.288, Human mean 0.485, Cohen's d = -2.08

    Complement to global sent_len_cv (which is whole-doc sentence CV, d=1.22
    on HC3 short Q&A): captures paragraph-internal monotony that a global
    CV averages out when paragraphs span different registers.

    Returns:
        dict with:
          - mean_cv: mean of per-paragraph sentence-length CVs
          - n_paragraphs_used: paragraphs that had >=3 sentences
          - n_paragraphs_total: total paragraph count after min-len filter
    """
    raw_paras = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in raw_paras
                  if p.strip() and len(_extract_chinese(p.strip())) >= 30]

    if len(paragraphs) < 3:
        return {
            'mean_cv': 0.0,
            'n_paragraphs_used': 0,
            'n_paragraphs_total': len(paragraphs),
        }

    cvs = []
    for p in paragraphs:
        parts = re.split(r'[。！？]', p)
        sents = [s.strip() for s in parts
                 if s.strip() and len(_extract_chinese(s.strip())) >= 5]
        if len(sents) < 3:
            continue
        sl = [len(_extract_chinese(s)) for s in sents]
        m = sum(sl) / len(sl)
        if m == 0:
            continue
        var = sum((l - m) ** 2 for l in sl) / len(sl)
        cvs.append((var ** 0.5) / m)

    if len(cvs) < 2:
        return {
            'mean_cv': 0.0,
            'n_paragraphs_used': len(cvs),
            'n_paragraphs_total': len(paragraphs),
        }

    return {
        'mean_cv': sum(cvs) / len(cvs),
        'n_paragraphs_used': len(cvs),
        'n_paragraphs_total': len(paragraphs),
    }


# ─── Combined Analysis ───

def analyze_text(text):
    """
    Run full statistical analysis on text.

    Returns dict with all metrics and AI likelihood indicators:
      - perplexity: overall perplexity
      - burstiness: CV of windowed perplexity
      - entropy_cv: CV of paragraph entropy
      - diveye: dict of DivEye-style surprisal features (autocorr, spectral flatness, shape)
      - indicators: dict of boolean flags for AI-like patterns
    """
    chars = _extract_chinese(text)
    char_count = len(chars)

    if char_count < 30:
        return {
            'perplexity': 0.0,
            'burstiness': 0.0,
            'entropy_cv': 0.0,
            'char_count': char_count,
            'diveye': {},
            'indicators': {
                'low_perplexity': False,
                'low_burstiness': False,
                'uniform_entropy': False,
                'flat_surprisal_spectrum': False,
                'low_surprisal_autocorr': False,
            },
            'details': {},
        }

    # Perplexity
    ppl_result = compute_perplexity(text, window_size=50)

    # Burstiness
    burst_result = compute_burstiness(text, window_size=50)

    # Entropy uniformity
    ent_result = compute_entropy_uniformity(text)

    # Per-paragraph sentence-length CV averaged (v5 P1 cycle 131,
    # longform calibration d = -2.08)
    para_slcv = compute_para_sent_len_cv(text)

    # Paragraph-length CV (v5 P1.2 cycle 135, longform calibration
    # d = -1.49). The binary trigger already fires in detect_cn at
    # CV<0.2; this exposes the continuous value to LR fusion so the
    # signal contributes on samples whose CV stays just above the rule
    # threshold.
    para_lcv = compute_paragraph_length_cv(text)

    # DivEye surprisal features — reuse log_probs from compute_perplexity
    diveye = compute_diveye_features(ppl_result.get('log_probs', []))

    # GLTR rank-bucket distribution
    gltr = compute_gltr_buckets(text)

    # Sentence-length burstiness (CNKI 语言模式链 / AIMS 2025)
    sent_len = compute_sentence_length_features(text)

    # Punctuation density (HC3-Chinese calibration 2026-04-19)
    punct = compute_punctuation_density(text)

    # Transition-word density (CNKI 语义逻辑链 / HC3 2026-04-19)
    trans = compute_transition_density(text)

    # DetectGPT-lite curvature (Fast-DetectGPT-style, HC3 2026-04-19 cycle 10)
    curv = compute_curvature(text)

    # Binoculars dual ngram ratio (B-path cycle 23, gated on secondary ngram file)
    bino = compute_binoculars_ratio(text)

    # Wikipedia ngram divergence (F-3 2026-04-22, gated on wiki ngram file)
    wiki = compute_wiki_lp_diff(text)

    # News ngram divergence (F-11 2026-04-22, THUCNews-derived)
    news = compute_news_lp_diff(text)

    # Char-level MATTR (E-8, arxiv 2507.15092 PATTR-lite)
    char_mattr = compute_char_mattr(text, window=100)

    # F-path multi-scale: unigram ppl and its ratio to trigram ppl.
    # HC3 pilot: uni_ppl alone d=0.08, uni/tri_ratio d=0.31 (AI concentrates
    # common chars differently from humans, most visible in the ratio).
    uni_ppl = compute_unigram_perplexity(text)
    uni_tri_ratio = uni_ppl / ppl_result['perplexity'] if ppl_result.get('perplexity', 0) > 0 else 0.0

    # Thresholds — conservative, designed for character-level n-gram model.
    #
    # With a small corpus-based model, perplexity direction depends on text style.
    # We use RELATIVE signals rather than absolute thresholds:
    #   - Perplexity: AI formal text often has moderate-high ppl from this model
    #     (formal vocab not well covered), BUT the KEY signal is the range 100-400
    #     which is typical of formulaic AI text using semi-common formal patterns.
    #   - Burstiness: how much perplexity varies across windows.
    #     Very low values (< 0.12) = uniform complexity = AI-like.
    #     BUT short texts have unreliable burstiness, so require enough windows.
    #   - Entropy CV: how uniform paragraph entropy is.
    #     Very low values (< 0.05) = uniform paragraph structure = AI-like.
    #
    # These are intentionally conservative to avoid false positives.
    # With longer texts (1000+ chars) and better frequency data, accuracy improves.

    ppl = ppl_result['perplexity']
    burst = burst_result['burstiness']
    ent_cv = ent_result['entropy_cv']
    n_windows = burst_result['n_windows']
    n_paras = ent_result['n_paragraphs']
    para_slcv_mean = para_slcv['mean_cv']
    para_slcv_n = para_slcv['n_paragraphs_used']

    # DivEye thresholds calibrated on 100-pair HC3-Chinese sample (Cohen's d > 0.25):
    #   Feature          human_median   ai_median   Cohen_d
    #   skew             1.514          1.315       0.41
    #   excess_kurt      0.716          0.035       0.29
    #   spectral_flatness (auxiliary; d ~0.20)
    #
    # Burstiness/entropy_cv had Cohen's d < 0.1 on HC3 — essentially no signal
    # against naturally-written ChatGPT. Kept as indicators for backward compatibility
    # and because they still catch the stereotyped AI text the project originally targeted.
    gltr_top10 = gltr.get('proportions', {}).get('top10', 0.0) if gltr else 0.0
    indicators = {
        # Perplexity in the "formulaic formal" range (100-500) with enough text
        'low_perplexity': 50 < ppl < 500 and char_count >= 200,
        # Very low burstiness with enough data points (stereotyped AI)
        'low_burstiness': burst < 0.12 and n_windows >= 6,
        # Very uniform paragraph entropy with enough paragraphs (stereotyped AI)
        'uniform_entropy': ent_cv < 0.05 and n_paras >= 3,
        # DivEye: low skewness of per-char log-prob = fewer outlier "creative" choices
        'low_surprisal_skew': (
            diveye.get('skew', 2.0) < 1.35 and char_count >= 150
        ),
        # DivEye: low kurt = thinner tails = uniform predictability (AI-like)
        'low_surprisal_kurt': (
            diveye.get('excess_kurt', 1.0) < 0.35 and char_count >= 150
        ),
        # GLTR: high top-10 bucket proportion = AI picks from top-probability continuations
        # Threshold 0.21 from HC3 midpoint between human (0.19) and AI (0.22) means.
        'high_top10_bucket': (
            gltr_top10 > 0.21 and char_count >= 150
        ),
        # Sentence-length CV: AI writes formulaic sentences with low length variance.
        # HC3-Chinese 300+300 calibration (2026-04-19):
        #   human mean CV 0.52, AI mean CV 0.32, Cohen's d = 1.22
        # Threshold 0.40 — best tradeoff (flags 81% AI vs 29% human, spread 52%).
        'low_sentence_length_cv': (
            sent_len.get('cv', 1.0) < 0.40 and sent_len.get('n_sentences', 0) >= 5
        ),
        # Short-sentence fraction: humans frequently write < 10-char sentences,
        # AI rarely does. HC3 calibration: human mean 24.9%, AI mean 2.6%, d = 1.21.
        # Flag text with virtually no short sentences (< 8%).
        'low_short_sentence_fraction': (
            sent_len.get('short_frac', 1.0) < 0.08 and sent_len.get('n_sentences', 0) >= 5
        ),
        # Low comma density (HC3 d = -0.47): AI writes flowing prose with long
        # uninterrupted clauses; humans punctuate more. Threshold 4.5 per 100 chars
        # flags 76% AI vs 44% human (spread 31%).
        'low_comma_density': (
            punct.get('comma_density', 10.0) < 4.5 and char_count >= 100
        ),
        # High transition density — tried at cap 40 cycle A-2, marginal gap gain
        # (+0.6) but 1pt correct-rate drop. Still disabled. Humanize-side work
        # (cycle 12/13 transition replacements) already captures this signal.
        'high_transition_density': False,
        # DetectGPT-lite curvature — tried at cap 40 cycle A-2, didn't help
        # (correlates with transition density, noise > signal at this stage).
        # Disabled again, function kept.
        'high_curvature': False,
        # Binoculars dual ngram divergence (B-path cycle 23, disabled).
        # HC3 300+300 calibration showed strong Cohen's d = 1.09, but at
        # detect_cn's 40-pt stat cap the indicator correlates with existing
        # signals enough that human avg bumps roughly as much as AI avg,
        # net-net reducing the gap (75% / 14.7 → 74% / 13.4 with weight 6
        # + tight threshold). Same saturation issue that parked cycle 8
        # transition density (d=0.62) and cycle 10 curvature (d=0.77).
        # `compute_binoculars_ratio` function, cycled training data,
        # and detect_cn wiring all remain in place for future use when
        # the stat scoring architecture allows more simultaneous indicators
        # (Ghostbuster-style LR ensemble or sigmoid-soft-cap).
        'low_binoculars_diff': False,
        # MATTR lexical diversity (E-8 cycle 40, arxiv 2507.15092 PATTR-lite).
        # HC3 300+300: AI mean 0.6274, human mean 0.6805, Cohen's d = 0.700.
        # Threshold 0.58 — tighter than midpoint 0.65 because midpoint flagged
        # too many humans and dropped correct 75→73%. Even at 0.58 still
        # dropped correct to 74%. MATTR correlates with other stat indicators
        # (perplexity, gltr) enough to contribute marginal negative under the
        # 40-pt stat cap. Kept function + metric + wiring for future Ghostbuster
        # LR ensemble; indicator disabled for now like binoculars/curvature.
        'low_char_mattr': False,
        # Per-paragraph sentence-length CV averaged (v5 P1 cycle 131,
        # calibration 2026-04-29 n=50 longform: AI mean 0.288,
        # Human mean 0.485, Cohen's d = -2.08). Threshold 0.35 between
        # the two means; requires >=2 paragraphs with >=3 sentences each.
        'low_para_sent_len_cv': (
            para_slcv_mean > 0 and para_slcv_mean < 0.35 and para_slcv_n >= 2
        ),
    }

    return {
        'perplexity': ppl,
        'burstiness': burst,
        'entropy_cv': ent_cv,
        'char_count': char_count,
        'diveye': diveye,
        'gltr': gltr if gltr else {},
        'sent_len': sent_len,
        'punct': punct,
        'trans': trans,
        'curv': curv,
        'bino': bino,
        'wiki': wiki,
        'news': news,
        'char_mattr': char_mattr,
        'para_slcv': para_slcv,
        'para_lcv': para_lcv,
        'uni_ppl': uni_ppl,
        'uni_tri_ratio': uni_tri_ratio,
        'indicators': indicators,
        'details': {
            'perplexity_result': {
                'perplexity': ppl_result['perplexity'],
                'avg_log_prob': ppl_result['avg_log_prob'],
                'n_windows': len(ppl_result['window_perplexities']),
            },
            'burstiness_result': {
                'burstiness': burst_result['burstiness'],
                'mean_ppl': burst_result['mean_ppl'],
                'std_ppl': burst_result['std_ppl'],
                'n_windows': burst_result['n_windows'],
            },
            'entropy_result': {
                'entropy_cv': ent_result['entropy_cv'],
                'mean_entropy': ent_result['mean_entropy'],
                'n_paragraphs': ent_result['n_paragraphs'],
            },
        },
    }


# ─── LR ensemble feature extraction (F-path F-2) ───

LR_FEATURE_NAMES = (
    'perplexity',
    'burstiness',
    'entropy_cv',
    'diveye_skew',
    'diveye_excess_kurt',
    'diveye_spectral_flatness',
    'diveye_autocorr_lag1',
    'gltr_top10_frac',
    'gltr_top100_frac',
    'sent_len_cv',
    'sent_len_short_frac',
    'sent_len_long_frac',
    'sent_len_equal_mid_frac',
    'punct_comma_density',
    'punct_density',
    'trans_density',
    'curv_mean',
    'bino_lp_diff',
    'uni_tri_ratio',        # F-2 multi-scale ratio, HC3 d=0.31
    'wiki_vs_human',        # F-3 2026-04-22, HC3 d=1.58
    'wiki_vs_primary',      # F-3 2026-04-22, HC3 d=1.13
    'news_vs_human',        # F-11 2026-04-22, HC3 d=1.20 (on 10-category news corpus)
    'para_sent_len_cv_avg', # v5 P1 2026-04-29, longform d=-2.08 (multi-paragraph only)
    'paragraph_length_cv',  # v5 P1.2 2026-04-29, longform d=-1.49 (multi-paragraph only)
)


_LR_COEF_CACHE = {}
_LR_COEF_FILE = os.path.join(SCRIPT_DIR, 'lr_coef_cn.json')
_LR_COEF_ACADEMIC_FILE = os.path.join(SCRIPT_DIR, 'lr_coef_academic.json')
_LR_COEF_LONGFORM_FILE = os.path.join(SCRIPT_DIR, 'lr_coef_longform.json')


def _load_lr_coef(path=None, scene='general'):
    """Load LR coefficients + scaler stats from JSON. Cached per file.

    scene: 'general' -> lr_coef_cn.json; 'academic' -> lr_coef_academic.json;
    'novel' / 'longform' -> lr_coef_longform.json (trained on AI long-form
    + human novel/news corpora). Falls back to general if the scene file
    is absent.
    """
    if path is None:
        if scene == 'academic' and os.path.exists(_LR_COEF_ACADEMIC_FILE):
            path = _LR_COEF_ACADEMIC_FILE
        elif scene in ('novel', 'longform') and os.path.exists(_LR_COEF_LONGFORM_FILE):
            path = _LR_COEF_LONGFORM_FILE
        else:
            path = _LR_COEF_FILE
    if path in _LR_COEF_CACHE:
        return _LR_COEF_CACHE[path]
    if not os.path.exists(path):
        _LR_COEF_CACHE[path] = None
        return None
    import json
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    data['_path'] = path
    _LR_COEF_CACHE[path] = data
    return data


def _auto_scene(text_or_analysis, short_thresh=1500):
    """Choose scene by text length. Long text (>= 1500 Chinese chars)
    routes to the long-form LR; shorter text stays on general. Academic
    is never auto-selected — users must opt in explicitly."""
    if isinstance(text_or_analysis, str):
        cn = sum(1 for c in text_or_analysis if '\u4e00' <= c <= '\u9fff')
    else:
        cn = text_or_analysis.get('char_count', 0)
    return 'novel' if cn >= short_thresh else 'general'


def compute_lr_score(text_or_analysis, coef_path=None, scene='general'):
    """Score text via LR ensemble. Returns dict with p_ai, score_0_100,
    and feature contributions.

    scene: 'general' (default) uses lr_coef_cn.json; 'academic' uses
    lr_coef_academic.json; 'novel'/'longform' uses lr_coef_longform.json;
    'auto' routes to novel for long text (>= 1500 Chinese chars) and
    general otherwise. Explicit coef_path overrides scene.
    Returns None if the requested coef file is absent.
    """
    if scene == 'auto':
        scene = _auto_scene(text_or_analysis)
    coef = _load_lr_coef(coef_path, scene=scene)
    if coef is None:
        return None

    vec, names = extract_feature_vector(text_or_analysis)
    means = coef['mean']
    scales = coef['scale']
    weights = coef['coef']
    intercept = coef['intercept']

    # Standardize then compute logit. Slice to len(weights) so older coef files
    # (trained with fewer features) remain compatible with newer feature vectors.
    n = min(len(weights), len(vec))
    standardized = [(vec[i] - means[i]) / (scales[i] if scales[i] else 1.0)
                    for i in range(n)]
    logit = intercept + sum(standardized[i] * weights[i] for i in range(n))
    import math as _m
    # Clamp to avoid overflow
    if logit > 500:
        p_ai = 1.0
    elif logit < -500:
        p_ai = 0.0
    else:
        p_ai = 1.0 / (1.0 + _m.exp(-logit))
    score = round(100 * p_ai)

    contribs = [(names[i], standardized[i] * weights[i]) for i in range(n)]
    contribs.sort(key=lambda x: -abs(x[1]))

    return {
        'p_ai': p_ai,
        'score': score,
        'logit': logit,
        'top_contributions': contribs[:5],
        'features': dict(zip(names, vec)),
    }


def extract_feature_vector(text_or_analysis):
    """Flatten analyze_text output into a fixed-length 18-feature vector for LR.

    Accepts either raw text (re-runs analyze_text) or a pre-computed analysis
    dict (saves one full pass when upstream already has it).

    Returns (vector, names) where vector is list of 18 floats in LR_FEATURE_NAMES
    order. All features are continuous; missing/unavailable features default to
    0.0 (e.g., Binoculars returns 0 when secondary ngram file absent).
    """
    if isinstance(text_or_analysis, str):
        analysis = analyze_text(text_or_analysis)
    else:
        analysis = text_or_analysis

    diveye = analysis.get('diveye', {}) or {}
    gltr = analysis.get('gltr', {}) or {}
    gltr_props = gltr.get('proportions', {}) if gltr else {}
    sent_len = analysis.get('sent_len', {}) or {}
    punct = analysis.get('punct', {}) or {}
    trans = analysis.get('trans', {}) or {}
    curv = analysis.get('curv', {}) or {}
    bino = analysis.get('bino', {}) or {}
    wiki = analysis.get('wiki', {}) or {}
    news = analysis.get('news', {}) or {}
    para_slcv = analysis.get('para_slcv', {}) or {}
    para_lcv = analysis.get('para_lcv', {}) or {}

    vec = [
        float(analysis.get('perplexity') or 0.0),
        float(analysis.get('burstiness') or 0.0),
        float(analysis.get('entropy_cv') or 0.0),
        float(diveye.get('skew') or 0.0),
        float(diveye.get('excess_kurt') or 0.0),
        float(diveye.get('spectral_flatness') or 0.0),
        float(diveye.get('autocorr_lag1') or 0.0),
        float(gltr_props.get('top10') or 0.0),
        float(gltr_props.get('top100') or 0.0),  # mid-rank analog
        float(sent_len.get('cv') or 0.0),
        float(sent_len.get('short_frac') or 0.0),
        float(sent_len.get('long_frac') or 0.0),
        float(sent_len.get('equal_mid_frac') or 0.0),
        float(punct.get('comma_density') or 0.0),
        float(punct.get('punct_density') or 0.0),
        float(trans.get('density') or 0.0),
        float(curv.get('curvature_mean') or 0.0),
        float(bino.get('mean_lp_diff') or 0.0),
        float(analysis.get('uni_tri_ratio') or 0.0),
        float(wiki.get('wiki_vs_human') or 0.0),
        float(wiki.get('wiki_vs_primary') or 0.0),
        float(news.get('news_vs_human') or 0.0),
        float(para_slcv.get('mean_cv') or 0.0),
        float(para_lcv.get('cv') or 0.0),
    ]
    return vec, list(LR_FEATURE_NAMES)


# ─── CLI ───

def main():
    import argparse

    parser = argparse.ArgumentParser(description='中文文本 N-gram 统计分析 — 困惑度/突发度/熵')
    parser.add_argument('file', nargs='?', help='输入文件路径（不指定则从 stdin 读取）')
    parser.add_argument('-j', '--json', action='store_true', help='JSON 输出')
    parser.add_argument('-v', '--verbose', action='store_true', help='详细模式')
    args = parser.parse_args()

    import sys
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

    result = analyze_text(text)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Human-readable output
    ppl = result['perplexity']
    burst = result['burstiness']
    ent_cv = result['entropy_cv']
    indicators = result['indicators']

    print(f'字符数: {result["char_count"]}')
    print(f'困惑度 (perplexity): {ppl:.1f}')
    print(f'突发度 (burstiness):  {burst:.3f}')
    print(f'段落熵变异 (entropy CV): {ent_cv:.3f}')
    print()

    print('── AI 特征判断 ──')
    for key, desc in [
        ('low_perplexity', '困惑度异常低（过于流畅/可预测）'),
        ('low_burstiness', '困惑度变化过于均匀（缺少起伏）'),
        ('uniform_entropy', '段落间熵值分布过于均匀'),
    ]:
        flag = '⚠️  是' if indicators[key] else '✅ 否'
        print(f'  {flag} — {desc}')

    if args.verbose and result['details']:
        print()
        print('── 详细数据 ──')
        d = result['details']
        print(f'  平均 log2 概率: {d["perplexity_result"]["avg_log_prob"]:.3f}')
        print(f'  窗口数: {d["burstiness_result"]["n_windows"]}')
        print(f'  窗口平均困惑度: {d["burstiness_result"]["mean_ppl"]:.1f}')
        print(f'  窗口困惑度标准差: {d["burstiness_result"]["std_ppl"]:.1f}')
        print(f'  段落数: {d["entropy_result"]["n_paragraphs"]}')
        print(f'  段落平均熵: {d["entropy_result"]["mean_entropy"]:.3f}')


if __name__ == '__main__':
    main()
