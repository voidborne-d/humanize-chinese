# 🔧 中文 AI 文本去痕迹工具

**免费、本地运行、零依赖的中文 AI 文本检测与改写工具。**

[![GitHub stars](https://img.shields.io/github/stars/voidborne-d/humanize-chinese?style=flat-square)](https://github.com/voidborne-d/humanize-chinese)
[![ClawHub](https://img.shields.io/badge/clawhub-humanize--chinese-blue?style=flat-square)](https://clawhub.com/skills/humanize-chinese)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.6+-blue?style=flat-square)](https://python.org)

检测 20+ 种 AI 写作模式 + N-gram 困惑度统计分析，量化评分 0-100，支持 7 种风格转换，学术论文 AIGC 降重专用模式。纯 Python，不需要安装任何依赖包。

---

## Features at a Glance

| 功能 | 说明 |
|------|------|
| 🔍 AI 检测 | 20+ 规则维度 + N-gram 困惑度统计，加权 0-100 评分，精确到句子级 |
| 📈 统计分析 | 困惑度 / 突发度 / 段落熵均匀度，从概率分布层面检测 AI |
| ✏️ 智能改写 | 困惑度引导选词 + 低频 bigram 注入 + 句长随机化 + 噪声表达 |
| 🎓 学术降重 | 10 维度检测 + 120 条学术替换词库，针对知网/维普/万方 |
| 🎨 风格转换 | 知乎、小红书、公众号、微博、学术、文艺、口语 7 种 |
| 📊 前后对比 | 一键对比改写前后评分变化 |
| 🔄 可复现 | `--seed` 参数保证相同输入输出一致 |
| 📦 零依赖 | 纯 Python 标准库，下载即用 |

---

## Comparison / 对比

和目前最流行的中文去 AI 工具 [Humanizer-zh](https://github.com/op7418/Humanizer-zh) 的对比：

| 对比项 | humanize-chinese（本项目） | Humanizer-zh |
|--------|--------------------------|--------------|
| 运行方式 | ✅ 独立 CLI 工具，终端直接跑 | ❌ 纯 Skill prompt，必须在 Claude Code 内用 |
| 依赖 | ✅ 零依赖（纯 Python 标准库） | 需要 Claude Code 环境 |
| 量化评分 | ✅ 0-100 分，4 级评估 | ❌ 无评分，靠感觉判断 |
| 统计检测 | ✅ N-gram 困惑度 + 突发度 + 熵分析 | ❌ 无统计特征 |
| 句子级分析 | ✅ 定位最可疑的句子 | ❌ 只做整体改写 |
| 学术论文模式 | ✅ 专用 10 维度检测 + 120 条替换 | ❌ 无学术专用功能 |
| 风格转换 | ✅ 7 种中文写作风格 | ❌ 无 |
| 结果可复现 | ✅ `--seed` 固定随机数 | ❌ 每次结果不同 |
| 批量处理 | ✅ CLI 管道，脚本化 | ❌ 只能单篇交互 |
| 模式配置 | ✅ JSON 外部配置，可自定义 | ❌ 硬编码在 prompt 里 |
| 免费 | ✅ 完全免费 | ⚠️ 需要 Claude API 额度 |
| 也可作为 Skill | ✅ 支持 OpenClaw / Claude Code | ✅ 支持 Claude Code |

简单说：Humanizer-zh 是个很好的 prompt，但它只能在 Claude Code 里用，没法量化效果，也没有学术论文专用功能。我们这个是独立工具，可以在任何环境里跑，有评分有对比，学术场景也覆盖了。

---

## Install / 安装

**方式一：ClawHub（推荐）**

```bash
clawhub install humanize-chinese
```

**方式二：Git Clone**

```bash
git clone https://github.com/voidborne-d/humanize-chinese.git
cd humanize-chinese
```

**方式三：Claude Code Skill**

```bash
# 通过 npx 安装
npx skills add https://github.com/voidborne-d/humanize-chinese.git
```

**方式四：手动下载**

直接下载 `scripts/` 目录下的 Python 文件和 `patterns_cn.json`，放到同一个目录就能用。

---

## Quick Start

### 场景一：通用文本去 AI 味

```bash
# 先检测，看看 AI 味有多重
python scripts/detect_cn.py text.txt -v

# 改写 + 对比
python scripts/compare_cn.py text.txt -a -o clean.txt

# 验证效果
python scripts/detect_cn.py clean.txt -s
```

### 场景二：学术论文 AIGC 降重

```bash
# 检测学术 AI 痕迹
python scripts/academic_cn.py paper.txt

# 改写并对比（推荐）
python scripts/academic_cn.py paper.txt -o clean.txt --compare

# 激进模式（降得更狠）
python scripts/academic_cn.py paper.txt -o clean.txt -a --compare
```

### 场景三：风格转换

```bash
# 转小红书风格
python scripts/style_cn.py text.txt --style xiaohongshu

# 转知乎风格
python scripts/style_cn.py text.txt --style zhihu -o zhihu.txt

# 先去 AI 味再转风格
python scripts/humanize_cn.py text.txt --style xiaohongshu -o xhs.txt
```

---

## Examples / 改写效果展示

### 通用文本

**改写前**（AI 评分：87/100 VERY HIGH）：

> 综上所述，人工智能技术在教育领域具有重要的应用价值和广阔的发展前景。值得注意的是，随着技术的不断发展，AI 将在个性化学习、智能评估等方面发挥越来越重要的作用，为教育行业的数字化转型赋能。

**改写后**（AI 评分：12/100 LOW）：

> 从目前的实践来看，AI 辅助教学在个性化推荐方面效果比较明显，但在情感交互层面仍有不少局限。技术落地不是一蹴而就的事，教育场景的复杂性远超一般的商业应用。

### 学术论文

**改写前**（AIGC 评分：100/100 VERY HIGH）：

> 随着社会的不断发展，人工智能技术在教育领域的应用引起了广泛关注。本文旨在探讨人工智能对高等教育教学模式的影响，具有重要的理论意义和实践价值。研究表明，人工智能技术已被广泛应用于课堂教学、学生评估和个性化学习等多个方面，发挥着重要作用。

**改写后**（AIGC 评分：26/100 MEDIUM，降低 74 分）：

> 近年来社会变迁加速，人工智能技术在教育领域的应用逐渐进入研究者的视野。本文尝试探讨人工智能对高等教育教学模式的影响，兼具理论探索与实践参考的双重价值。前人研究发现，人工智能技术已广泛用于课堂教学、学生评估和个性化学习等多个方面，扮演着不可或缺的角色。

### 社交媒体

**改写前**（AI 评分：72/100 HIGH）：

> 在当今快节奏的生活中，时间管理具有至关重要的意义。通过合理规划时间，不仅能够提升工作效率，更能实现工作与生活的平衡。值得一提的是，良好的时间管理习惯需要长期培养和不断优化。

**改写后**（小红书风格，AI 评分：8/100 LOW）：

> 姐妹们！说真的，时间管理这事我踩过太多坑了 😭 之前天天加班到半夜，后来摸索出一套方法，现在居然能准点下班了？！重点就是别给自己排太满，留点缓冲时间。这个习惯我养了大概三个月才稳定下来，急不来的～

---

## Scoring / 评分标准

| 分数 | 等级 | 含义 |
|------|------|------|
| 0-24 | 🟢 LOW | 基本像人写的 |
| 25-49 | 🟡 MEDIUM | 有些 AI 痕迹 |
| 50-74 | 🟠 HIGH | 大概率是 AI 生成 |
| 75-100 | 🔴 VERY HIGH | 几乎可以确定是 AI |

### 检测维度

**🔴 高权重（容易暴露）：** 三段式套路（首先/其次/最后）、机械连接词（综上所述/值得注意的是）、空洞宏大词（赋能/闭环/数字化转型）

**🟠 中权重：** AI 高频词（助力/彰显/底层逻辑）、填充短语、平衡论述模板、套话句式

**🟡 低权重：** 犹豫语过多、列举成瘾、标点滥用、修辞堆砌

**⚪ 风格信号：** 段落长度均匀、句长单调、情感平淡、开头重复、信息熵低

**📊 统计特征（v2.2 新增）：** 基于字符级 N-gram 语言模型的统计检测。不再只"看词"，而是"看分布"——从概率层面检测 AI 生成痕迹：

| 指标 | 说明 | AI 文本 | 人类文本 |
|------|------|---------|----------|
| 困惑度 (Perplexity) | 文本在 N-gram 模型下的可预测程度 | ~231（低 = 更可预测） | ~533（高 = 更自然） |
| 突发度 (Burstiness) | 困惑度在滑动窗口间的变异系数 | 均匀（AI 复杂度恒定） | 有起伏（人类时简时繁） |
| 段落熵均匀度 | 段落间信息熵的变异系数 | 各段结构高度一致 | 段落间差异大 |

为什么加这个？传统规则检测只抓"像不像 AI 的样子"（表面特征），统计检测抓的是"是不是从语言模型采样的"（分布特征）。两层叠加，漏网率更低。

统计特征占总评分的 20-25%，作为规则检测的补充信号。基于预计算的中文字符 bigram/trigram 频率表（`scripts/ngram_freq_cn.json`），覆盖新闻、学术、社交、文学等多种文体。

独立使用统计分析：

```bash
python scripts/ngram_model.py your_text.txt
```

### 改写引擎的困惑度反馈（v2.3 新增）

改写不再是盲目替换。每次替换词/短语时，引擎会：

1. 列出所有候选替换（比如"综上所述"可以换成"总之"、"回顾以上讨论"、"简单说"等）
2. 逐一计算替换后句子的困惑度
3. **选困惑度最高的那个**（最不可预测 = 最像人写的）

另外还有两个机制：
- **Burstiness 守卫**：句式重组（合并/拆分）后如果文本 burstiness 下降超 20%（变得更均匀了），自动回退，不做这次重组
- **验证循环**：改写完成后整体测困惑度，如果还是太低，对最差的句子做第二轮替换

实测效果（学术论文改写）：

| | 原文 | 纯规则改写 | **v2.3 统计引导改写** |
|---|---|---|---|
| Perplexity | 173.9 | 185.2 | **212.0** (+22%) |
| Burstiness | 0.539 | 0.443 | **0.583** (+31%) |

用 `--no-stats` 可以关闭统计优化，回退到纯规则替换（更快，但效果差一些）。

### 深度改写策略（v2.4 新增）

在困惑度反馈的基础上，v2.4 加入了三个从 n-gram 分布层面优化的策略：

**1. 低频 bigram 注入**
扫描文本中频率最高的字组合（最可预测），用 109 个词的同义替换表换成低频同义词。不是从"套话 A"换成"套话 B"，而是从 n-gram 频率表反推"哪个字该换"。

**2. 句子长度随机化**
AI 写作几乎每句 20-40 字，人类写作忽长忽短。随机合并短句、截断中等句，制造不均匀的节奏。

**3. 噪声表达插入**
在适当位置加入犹豫语、自我修正、不确定标记等人类写作特有的表达。学术模式自动过滤口语化表达。

效果：

| 文本类型 | 原文 | v2.3 | **v2.4 normal** | **v2.4 aggressive** | 人类参考 |
|---|---|---|---|---|---|
| 通用文本 | 231 | 300 | **306** | **348** | ~533 |
| 学术论文 | 174 | 212 | **273** | **326** | ~533 |

用 `--no-noise` 跳过策略 2、3（只做词级替换），用 `-a` 开启激进模式。

---

## 🎓 学生党必看：免费降 AIGC 率

用 ChatGPT 写了论文初稿，担心知网/维普查出来？这个工具就是干这个的。

### 三步走

```bash
# 1. 先看看你的论文 AIGC 率多高
python scripts/academic_cn.py 论文.txt

# 2. 一键改写
python scripts/academic_cn.py 论文.txt -o 改后.txt --compare

# 3. 不放心就开激进模式
python scripts/academic_cn.py 论文.txt -o 改后.txt -a --compare
```

### 这工具干了啥

- 把"本文旨在""具有重要意义"这种 AI 套话换成正常的学术表达
- 减少被动句（"被广泛应用"→"得到较多运用"）
- 打破每段都一样长的结构
- 加入学术犹豫语（"可能""在一定程度上"），让语气没那么绝对
- 把"研究表明"换成"笔者认为""前人研究发现"，增加作者存在感
- 给结论补上局限性讨论

### 注意

⚠️ 工具只做文本风格调整，**不会改变你的论证逻辑和学术内容**。改完以后通读一遍，确认：
- 专业术语没被误改
- 论述逻辑没打乱
- 引用格式还对着
- 读起来通顺

建议改完以后自己用知网 AMLC 或维普跑一遍，确认效果。

---

## Writing Styles / 风格转换

| 风格 | 命令 | 适合场景 |
|------|------|----------|
| 口语化 | `--style casual` | 聊天、朋友圈 |
| 知乎 | `--style zhihu` | 深度回答、分析 |
| 小红书 | `--style xiaohongshu` | 种草、测评、生活分享 |
| 公众号 | `--style wechat` | 推文、专栏 |
| 学术 | `--style academic` | 论文、报告 |
| 文艺 | `--style literary` | 散文、随笔 |
| 微博 | `--style weibo` | 短评、热点 |

---

## CLI Reference

```bash
# 检测
python scripts/detect_cn.py [file] [-v] [-s] [-j] [--sentences N]

# 改写
python scripts/humanize_cn.py [file] [-o out] [--scene S] [--style S] [-a] [--seed N]

# 风格转换
python scripts/style_cn.py [file] --style S [-o out] [--seed N] [--list]

# 学术降重
python scripts/academic_cn.py [file] [-o out] [--detect-only] [-a] [--compare] [-j] [-s] [-v]

# 对比
python scripts/compare_cn.py [file] [-o out] [--scene S] [--style S] [-a]
```

### 常用参数

| 参数 | 说明 |
|------|------|
| `-v` | 详细模式，显示最可疑的句子 |
| `-s` | 只输出评分（如 `72/100 (high)`） |
| `-j` | JSON 格式输出 |
| `-o` | 输出文件路径 |
| `-a` | 激进模式，改写力度更大 |
| `--seed N` | 固定随机种子，保证结果可复现 |
| `--scene` | 场景：general / social / tech / formal / chat |
| `--style` | 风格：casual / zhihu / xiaohongshu / wechat / academic / literary / weibo |
| `--compare` | 显示改写前后对比 |
| `--no-stats` | 关闭困惑度统计优化（更快，纯规则替换） |
| `--no-noise` | 关闭噪声注入和句长随机化（只做词级替换） |

---

## Customization / 自定义

所有检测模式、替换词库、权重配置都在 `scripts/patterns_cn.json` 里，可以自己改：

- 加新的 AI 词汇模式
- 调整评分权重
- 添加替换规则
- 修改正则匹配模式

---

## Batch Processing / 批量处理

```bash
# 批量检测
for f in *.txt; do echo "=== $f ===" && python scripts/detect_cn.py "$f" -s; done

# 批量改写
for f in *.md; do python scripts/humanize_cn.py "$f" -a -o "${f%.md}_clean.md"; done
```

---

## License

MIT — 随便用，不用付钱，不用署名。
