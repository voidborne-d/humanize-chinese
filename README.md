# humanize-chinese

Detect and humanize AI-generated Chinese text. Makes robotic AI writing natural and undetectable.

[![ClawHub](https://img.shields.io/badge/clawhub-humanize--chinese-blue)](https://clawhub.com/skills/humanize-chinese)

## Features

- **20+ detection categories** with weighted 0-100 scoring
- **Sentence-level analysis** — find the most AI-like sentences
- **Context-aware replacement** — regex patterns + plain text, longest-first
- **Sentence restructuring** — merge short, split long, vary rhythm
- **Vocabulary diversification** — reduce word repetition
- **7 writing styles** — casual, zhihu, xiaohongshu, wechat, academic, literary, weibo
- **External config** — all patterns in `patterns_cn.json`
- **Pure Python** — no dependencies

## Install

```bash
clawhub install humanize-chinese
```

Or clone:

```bash
git clone https://github.com/voidborne-d/humanize-chinese.git
```

## Quick Start

```bash
# Detect AI patterns
python scripts/detect_cn.py text.txt
python scripts/detect_cn.py text.txt -v    # verbose with worst sentences
python scripts/detect_cn.py text.txt -s    # score only: "72/100 (high)"

# Humanize
python scripts/humanize_cn.py text.txt -o clean.txt
python scripts/humanize_cn.py text.txt --scene tech -a   # aggressive mode

# Style transform
python scripts/style_cn.py text.txt --style xiaohongshu

# Compare before/after
python scripts/compare_cn.py text.txt --scene tech -a
```

## Scoring

| Score | Level | Meaning |
|-------|-------|---------|
| 0-24  | LOW | Likely human-written |
| 25-49 | MEDIUM | Some AI signals |
| 50-74 | HIGH | Probably AI-generated |
| 75-100 | VERY HIGH | Almost certainly AI |

## Detection Example

```
AI 评分: 100/100 [████████████████████] VERY HIGH
字符: 381 | 句子: 14 | 段落: 5
信息熵: 8.29 | 情感密度: 0.00%
问题总数: 25

🔴 三段式套路 (2)
   首先，值得注意的是...其次...最后
🔴 机械连接词 (9)
   值得注意的是, 综上所述, 总而言之...
🔴 空洞宏大词 (8)
   赋能, 闭环, 数字化转型...
🟠 AI 高频词 (3)
   助力, 彰显, 颠覆
🟠 模板句式 (2)
   随着...的不断发展, 在当今...时代
```

## Humanization Result

```
═══ 对比结果 ═══
原文:   100/100 [████████████████████] VERY_HIGH
改写后:  25/100 [█████░░░░░░░░░░░░░░░] MEDIUM
✅ 降低了 75 分
```

## Writing Styles

| Style | Name | Best For |
|-------|------|----------|
| `casual` | 口语化 | Social media, messaging |
| `zhihu` | 知乎 | Q&A, analysis |
| `xiaohongshu` | 小红书 | Reviews, lifestyle |
| `wechat` | 公众号 | Newsletters, articles |
| `academic` | 学术 | Papers, reports |
| `literary` | 文艺 | Creative writing |
| `weibo` | 微博 | Short posts |

## Customization

Edit `scripts/patterns_cn.json` to add/modify detection patterns, replacement alternatives, and scoring weights.

## License

MIT
