# Humanize Chinese AI Text

Detect and transform AI-generated Chinese text to make it natural and undetectable.

## Overview

This ClawHub skill identifies "AI flavor" (AI 味) in Chinese text and rewrites it to sound human-like. Based on comprehensive research of Chinese AI writing patterns from mainstream models (ChatGPT, DeepSeek, etc.).

## Features

- **12 detection categories** specific to Chinese AI text
- **Scene-specific humanization** (social media, tech blogs, formal articles, chat)
- **Pure Python** — no dependencies required
- **CLI-friendly** — supports files and stdin/stdout

## Quick Start

```bash
# Detect AI patterns
python scripts/detect_cn.py text.txt

# Humanize with default settings
python scripts/humanize_cn.py text.txt -o clean.txt

# Scene-specific humanization
python scripts/humanize_cn.py text.txt --scene social -o social.txt
python scripts/humanize_cn.py text.txt --scene tech -o tech.txt

# Compare before/after
python scripts/compare_cn.py text.txt -o clean.txt
```

## Detection Categories

### Critical (Immediate AI Detection)
- Three-part structure (首先...其次...最后)
- Mechanical connectors (值得注意的是, 综上所述)
- Empty grand words (赋能, 闭环, 智慧时代)

### High Signal
- AI high-frequency words (助力, 彰显, 凸显)
- Technical jargon misuse (解构, 量子纠缠 in non-tech context)
- Excessive rhetoric (对偶句 >2x, 排比句 >1x)

### Medium Signal
- Punctuation overuse (em dashes, semicolons)
- Obscure metaphors
- Uniform paragraph lengths

### Style Signal
- Low burstiness (monotonous sentence structure)
- Low perplexity (predictable word choices)
- Neutral tone (lack of emotion)

## Scene Styles

| Scene | Style | Use Case |
|-------|-------|----------|
| `social` | Casual, conversational | WeChat, Weibo, Xiaohongshu |
| `tech` | Professional but approachable | Tech blogs, documentation |
| `formal` | Rigorous but natural | Reports, articles |
| `chat` | Friendly, concise | Customer service, dialogue |

## Examples

### Social Media Transformation

**Before (AI):**
```
在当今这个智慧时代，人工智能技术正在深刻地改变着软件开发的方方面面。
首先，AI 编程助手能够显著提升代码编写效率。其次，它可以帮助开发者快速
理解复杂的代码逻辑。最后，AI 工具在代码审查和测试方面也展现出了巨大的
潜力。值得注意的是，我们在享受 AI 带来便利的同时，也应该保持独立思考
的能力。
```

**After (Human):**
```
AI 编程助手这两年确实火了，像 Copilot、Cursor 这些工具，写代码时自动
补全、生成测试用例，省了不少时间。尤其是看别人的代码，以前得翻半天文档，
现在 AI 直接给个解释，效率提升明显。

不过也有坑。有时候 AI 生成的代码看着能跑，实际逻辑有问题，调试反而更
花时间。而且太依赖它，自己的思考能力会不会退化？这事儿得掂量掂量。
```

## Scripts

### detect_cn.py
Scan for AI patterns and calculate AI probability.

```bash
python scripts/detect_cn.py text.txt        # Full report
python scripts/detect_cn.py text.txt -s     # Score only
python scripts/detect_cn.py text.txt -j     # JSON output
echo "文本" | python scripts/detect_cn.py   # From stdin
```

### humanize_cn.py
Transform AI text to human-like.

```bash
python scripts/humanize_cn.py text.txt              # Basic
python scripts/humanize_cn.py text.txt -o out.txt   # Save to file
python scripts/humanize_cn.py text.txt --scene social  # Scene-specific
python scripts/humanize_cn.py text.txt -a           # Aggressive mode
```

### compare_cn.py
Compare detection scores before and after.

```bash
python scripts/compare_cn.py text.txt
python scripts/compare_cn.py text.txt --scene tech -o clean.txt
```

## AI Probability Scoring

| Rating | Criteria |
|--------|----------|
| Very High | Critical patterns present (three-part, mechanical connectors, empty words) |
| High | >20 issues OR density >3% |
| Medium | >10 issues OR density >1.5% |
| Low | <10 issues AND density <1.5% |

## Research Base

This skill is based on comprehensive Chinese AI writing research:
- Tencent News: "Deconstructing 'AI Flavor'"
- 53AI: "Detection and Optimization of Article 'AI Flavor'"
- AIGCleaner and other de-AI tools
- Statistical analysis of major Chinese LLMs

## License

MIT

## Author

Created for ClawHub by voidborne-d
