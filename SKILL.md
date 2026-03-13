---
name: humanize-chinese
description: Detect and humanize AI-generated Chinese text. 20+ detection categories, weighted 0-100 scoring with sentence-level analysis, 7 style transforms (casual/zhihu/xiaohongshu/wechat/academic/literary/weibo), sentence restructuring, context-aware replacement. Pure Python, no dependencies. v2.0.0
allowed-tools:
  - Read
  - Write
  - Edit
  - exec
---

# Humanize Chinese AI Text v2.0

Comprehensive CLI for detecting and transforming Chinese AI-generated text. Makes robotic AI writing natural and human-like.

**v2.0 highlights:** weighted 0-100 scoring, sentence-level analysis, sentence restructuring (merge/split), context-aware replacement, rhythm variation, vocabulary diversification, 7 style transforms, external pattern config (`patterns_cn.json`).

## Quick Start

```bash
# Detect AI patterns (20+ categories, 0-100 score)
python scripts/detect_cn.py text.txt
python scripts/detect_cn.py text.txt -v          # verbose + worst sentences
python scripts/detect_cn.py text.txt -s           # score only
python scripts/detect_cn.py text.txt -j           # JSON output

# Humanize text
python scripts/humanize_cn.py text.txt -o clean.txt
python scripts/humanize_cn.py text.txt --scene social
python scripts/humanize_cn.py text.txt --scene tech -a   # aggressive mode
python scripts/humanize_cn.py text.txt --seed 42         # reproducible

# Apply writing styles
python scripts/style_cn.py text.txt --style zhihu -o zhihu.txt
python scripts/style_cn.py text.txt --style xiaohongshu
python scripts/style_cn.py --list

# Compare before/after
python scripts/compare_cn.py text.txt --scene tech -a
python scripts/compare_cn.py text.txt -o clean.txt
```

---

## Detection System

### Scoring

Weighted 0-100 score with 4 severity levels:

| Score | Level | Meaning |
|-------|-------|---------|
| 0-24  | LOW | Likely human-written |
| 25-49 | MEDIUM | Some AI signals |
| 50-74 | HIGH | Probably AI-generated |
| 75-100 | VERY HIGH | Almost certainly AI |

### Detection Categories

#### 🔴 Critical (weight: 8)
| Category | Examples |
|----------|----------|
| Three-Part Structure | 首先...其次...最后, 一方面...另一方面, 其一...其二...其三 |
| Mechanical Connectors | 值得注意的是, 综上所述, 不难发现, 归根结底, 由此可见 |
| Empty Grand Words | 赋能, 闭环, 数字化转型, 协同增效, 全方位, 多维度 |

#### 🟠 High Signal (weight: 4)
| Category | Examples |
|----------|----------|
| AI High-Frequency Words | 助力, 彰显, 底层逻辑, 抓手, 触达, 沉淀, 复盘 |
| Filler Phrases | 值得一提的是, 众所周知, 毫无疑问 |
| Balanced Arguments | 虽然...但是...同时, 既有...也有...更有 |
| Template Sentences | 随着...的不断发展, 在当今...时代, 作为...的重要组成部分 |

#### 🟡 Medium Signal (weight: 2)
| Category | Examples |
|----------|----------|
| Hedging Language | 在一定程度上, 某种程度上, 通常情况下 (>5 occurrences) |
| List Addiction | Excessive numbered/bulleted lists |
| Punctuation Overuse | Dense em dashes, semicolons |
| Excessive Rhetoric | 对偶/排比句过多 |

#### ⚪ Style Signal (weight: 1.5)
| Category | Description |
|----------|-------------|
| Uniform Paragraphs | Low CV in paragraph lengths |
| Low Burstiness | Monotonous sentence lengths |
| Emotional Flatness | Lack of emotional/personal expressions |
| Repetitive Starters | Same sentence starters >3 times |
| Low Entropy | Low character-level entropy (predictable text) |

### Sentence-Level Analysis

With `-v` (verbose) mode, the detector identifies the most AI-like sentences:

```
── 最可疑句子 ──
  1. [16分] 随着人工智能技术的不断发展，在当今数字化转型时代...
     原因: 数字化转型, 深度融合, 模板: 随着.*?的(不断)?发展
```

---

## Humanization Engine

### Transforms (applied in order)

1. **Structure cleanup** — Remove three-part structure (首先/其次/最后)
2. **Phrase replacement** — Context-aware replacement of AI phrases (regex patterns first, then plain text, longest-first matching)
3. **Sentence merge** — Merge overly short consecutive sentences
4. **Sentence split** — Split long sentences at natural breakpoints (但是/不过/同时)
5. **Punctuation normalization** — Reduce excessive semicolons, em dashes
6. **Vocabulary diversification** — Replace repeated words (进行/实现/提供 etc.) with synonyms
7. **Paragraph rhythm** — Vary uniform paragraph lengths (merge short, split long)
8. **Casual injection** — Add human expressions (scene-dependent)
9. **Paragraph shortening** — For social/chat scenes

### Scenes

| Scene | Casualness | Best For |
|-------|-----------|----------|
| `general` | 0.3 | Default, balanced |
| `social` | 0.7 | Social media, short posts |
| `tech` | 0.3 | Tech blogs, tutorials |
| `formal` | 0.1 | Formal articles, reports |
| `chat` | 0.8 | Conversations, messaging |

### Aggressive Mode (`-a`)

Adds +0.3 casualness, more colloquial expressions, stronger sentence restructuring. Typical score reduction: **60-80 points** on heavily AI-generated text.

### Reproducibility

Use `--seed N` for reproducible results (same input + seed = same output).

---

## Writing Style Transforms

7 specialized Chinese writing styles:

| Style | Name | Description |
|-------|------|-------------|
| `casual` | 口语化 | Like chatting with friends — natural, relaxed |
| `zhihu` | 知乎 | Rational, in-depth, personal opinions |
| `xiaohongshu` | 小红书 | Enthusiastic, emoji-rich, product-focused |
| `wechat` | 公众号 | Storytelling, engaging, relatable |
| `academic` | 学术 | Rigorous, precise, no colloquialisms |
| `literary` | 文艺 | Poetic, imagery-rich, metaphorical |
| `weibo` | 微博 | Short, opinionated, shareable |

### Combine humanize + style

```bash
python scripts/humanize_cn.py text.txt --style xiaohongshu -o xhs.txt
```

This first humanizes (removes AI patterns) then applies the style transform.

---

## External Configuration

All patterns, replacements, and scoring weights are in `scripts/patterns_cn.json`. Edit this file to:

- Add new AI vocabulary patterns
- Customize replacement alternatives
- Adjust scoring weights per severity
- Add regex patterns for template detection
- Set thresholds for hedging language detection

---

## Scripts Reference

### detect_cn.py

```bash
python scripts/detect_cn.py [file] [-j] [-s] [-v] [--sentences N]
```

| Flag | Description |
|------|-------------|
| `-j` | JSON output |
| `-s` | Score only (e.g. "72/100 (high)") |
| `-v` | Verbose: show worst sentences |
| `--sentences N` | Number of worst sentences to show (default: 5) |

### humanize_cn.py

```bash
python scripts/humanize_cn.py [file] [-o output] [--scene S] [--style S] [-a] [--seed N]
```

| Flag | Description |
|------|-------------|
| `-o` | Output file |
| `--scene` | general/social/tech/formal/chat |
| `--style` | casual/zhihu/xiaohongshu/wechat/academic/literary/weibo |
| `-a` | Aggressive mode |
| `--seed` | Random seed for reproducibility |

### style_cn.py

```bash
python scripts/style_cn.py [file] --style S [-o output] [--seed N] [--list]
```

### compare_cn.py

```bash
python scripts/compare_cn.py [file] [-o output] [--scene S] [--style S] [-a]
```

Shows score diff, category changes, and metric comparison before/after humanization.

---

## Workflow

```bash
# 1. Check AI score
python scripts/detect_cn.py document.txt -v

# 2. Humanize with comparison
python scripts/compare_cn.py document.txt --scene tech -a -o clean.txt

# 3. Verify improvement
python scripts/detect_cn.py clean.txt -s

# 4. Optional: apply specific style
python scripts/style_cn.py clean.txt --style zhihu -o final.txt
```

---

## Batch Processing

```bash
# Scan all files
for f in *.txt; do
  echo "=== $f ==="
  python scripts/detect_cn.py "$f" -s
done

# Transform all markdown
for f in *.md; do
  python scripts/humanize_cn.py "$f" --scene tech -a -o "${f%.md}_clean.md"
done
```
