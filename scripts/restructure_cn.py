#!/usr/bin/env python3
"""
Chinese Deep Restructuring Module v1.0
句级深度改写：句式变换、句子拆合、信息重排、废话删除。
纯 Python，零外部依赖。

设计原则：保守优先——宁可不变也不要变出语法错误。
每个正则模板都用 named groups 精确捕获，避免误匹配。
"""

import re
import random


# ═══════════════════════════════════════════════════════════════════
#  1. 句式结构变换 — 15 种常见模板
# ═══════════════════════════════════════════════════════════════════

# 每个模板: (compiled_regex, list_of_replacement_lambdas)
# lambda 接收 match 对象，返回替换后的字符串

_SENTENCE_TEMPLATES = []


def _build_templates():
    """构建句式变换模板列表。每个模板包含一个正则和多个候选变换函数。
    变换函数接收 re.Match 对象，返回重写后的字符串。
    """
    templates = []

    # ── 1. 通过X，Y能够Z（仅句首）──
    templates.append((
        re.compile(r'^\s*通过(?P<X>[\u4e00-\u9fff]{2,10})[，,]\s*(?P<Y>[\u4e00-\u9fff]{2,8})能够(?P<Z>[\u4e00-\u9fff]{2,15})'),
        [
            lambda m: f'{m.group("Y")}{m.group("Z")}，靠的是{m.group("X")}',
            lambda m: f'{m.group("X")}让{m.group("Y")}得以{m.group("Z")}',
        ]
    ))

    # ── 2. X在Y方面发挥着Z作用 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})在(?P<Y>[^，,。]{2,12})方面发挥着(?P<Z>[^，,。]{1,8})作用'),
        [
            lambda m: f'{m.group("Y")}方面，{m.group("X")}的{m.group("Z")}作用不容忽视',
            lambda m: f'就{m.group("Y")}而言，{m.group("X")}起到了{m.group("Z")}作用',
        ]
    ))

    # ── 3. 随着X的不断发展，Y正在Z ──
    templates.append((
        re.compile(r'随着(?P<X>[^，,。]{2,20})的不断(?:发展|进步|演进|深入|推进)[^，,。]*[，,]\s*(?P<Y>[^，,。]{2,12})正在(?P<Z>[^。！？]{2,25})'),
        [
            lambda m: f'{m.group("Y")}正在{m.group("Z")}，这背后是{m.group("X")}的持续推动',
            lambda m: f'{m.group("X")}持续推进，{m.group("Y")}也因此{m.group("Z")}',
        ]
    ))

    # ── 4. X不仅A，还B ──
    templates.append((
        re.compile(r'(?P<X>[\u4e00-\u9fff]{2,12})不仅(?P<A>[\u4e00-\u9fff]{2,20})[，,]\s*(?:还|也|更)(?P<B>[\u4e00-\u9fff]{2,20})'),
        [
            lambda m: f'{m.group("X")}{m.group("A")}。同时也{m.group("B")}',
        ]
    ))

    # ── 5. X对Y具有Z意义 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})对(?P<Y>[^，,。]{2,12})具有(?P<Z>[^，,。]{1,10})意义'),
        [
            lambda m: f'从{m.group("Y")}的角度看，{m.group("X")}的{m.group("Z")}意义值得关注',
            lambda m: f'{m.group("X")}之于{m.group("Y")}，有着{m.group("Z")}意义',
        ]
    ))

    # ── 6. X能够根据Y，Z ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})能够根据(?P<Y>[^，,。]{2,20})[，,]\s*(?P<Z>[^。！？]{2,25})'),
        [
            lambda m: f'根据{m.group("Y")}，{m.group("X")}可以{m.group("Z")}',
            lambda m: f'{m.group("X")}会参考{m.group("Y")}来{m.group("Z")}',
        ]
    ))

    # ── 7. X为Y提供了Z ──
    templates.append((
        re.compile(r'(?P<X>[\u4e00-\u9fff]{2,12})为(?P<Y>[\u4e00-\u9fff]{2,10})提供了(?P<Z>[\u4e00-\u9fff]{2,15})'),
        [
            lambda m: f'在{m.group("X")}的支持下，{m.group("Y")}获得了{m.group("Z")}',
        ]
    ))

    # ── 8. 基于X的Y能够Z ──
    templates.append((
        re.compile(r'基于(?P<X>[^，,。]{2,15})的(?P<Y>[^，,。]{2,12})能够(?P<Z>[^。！？]{2,25})'),
        [
            lambda m: f'以{m.group("X")}为基础，{m.group("Y")}可以做到{m.group("Z")}',
            lambda m: f'{m.group("Y")}依托{m.group("X")}，实现了{m.group("Z")}',
        ]
    ))

    # ── 9. X的出现也Y了Z ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})的(?:出现|引入|发展|应用)(?:也|更是)?(?:极大地|大大|显著)?(?P<Y>提高|提升|改善|增强|促进|推动|加速)了(?P<Z>[^。！？]{2,20})'),
        [
            lambda m: f'{m.group("Z")}得到了{m.group("Y").replace("提高","提升").replace("促进","推动")}，{m.group("X")}功不可没',
            lambda m: f'有了{m.group("X")}，{m.group("Z")}明显{m.group("Y").replace("提高","好转").replace("促进","加快")}',
        ]
    ))

    # ── 10. 通过X和Y，Z能够W（工具并列句式）──
    # 此模板仅匹配明确的工具短词，不匹配长名词算出啊
    templates.append((
        re.compile(r'^\s*通过(?P<X>[\u4e00-\u9fff]{2,6})和(?P<Y>[\u4e00-\u9fff]{2,6})[，,]\s*(?P<Z>[\u4e00-\u9fff]{2,8})能够(?P<W>[\u4e00-\u9fff]{2,12})'),
        [
            lambda m: f'{m.group("Z")}{m.group("W")}，靠的是{m.group("X")}和{m.group("Y")}',
        ]
    ))

    # ── 11. X正在从Y推动Z ──
    templates.append((
        re.compile(r'(?P<X>[\u4e00-\u9fff]{2,12})正在从(?P<Y>[\u4e00-\u9fff]{2,12})推动(?P<Z>[\u4e00-\u9fff]{2,15})'),
        [
            lambda m: f'在{m.group("Y")}上，{m.group("X")}持续推动着{m.group("Z")}',
        ]
    ))

    # ── 12. X使得/让Y成为可能 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})(?:使得|让)(?P<Y>[^，,。]{2,20})(?:成为可能|变得可能|得以实现)'),
        [
            lambda m: f'{m.group("Y")}之所以能实现，离不开{m.group("X")}',
            lambda m: f'正是{m.group("X")}，{m.group("Y")}才有了实现的基础',
        ]
    ))

    # ── 13. X是Y的重要/关键Z ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})是(?P<Y>[^，,。]{2,12})的(?P<Z>重要|关键|核心|主要)(?P<W>[^。！？]{1,8})'),
        [
            lambda m: f'对于{m.group("Y")}来说，{m.group("X")}的{m.group("W")}地位{m.group("Z").replace("重要","不可小觑").replace("关键","至关重要").replace("核心","居于核心").replace("主要","相当突出")}',
        ]
    ))

    # ── 14. 研究表明/研究发现，X ──
    templates.append((
        re.compile(r'(?:研究表明|研究发现|研究显示)[，,]\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'从已有研究来看，{m.group("X")}',
            lambda m: f'学界的研究指向一个结论：{m.group("X")}',
        ]
    ))

    # ── 15. 与此同时/同时，X也Y ──
    templates.append((
        re.compile(r'(?:与此同时|同时)[，,]\s*(?P<X>[^，,。]{2,15})(?:也|还|更)(?P<Y>[^。！？]{2,25})'),
        [
            lambda m: f'另一方面，{m.group("X")}{m.group("Y")}',
            lambda m: f'{m.group("X")}同样{m.group("Y")}，这一点也不容忽视',
        ]
    ))

    return templates


_SENTENCE_TEMPLATES = _build_templates()


def restructure_sentences(text, strength=0.6):
    """对文本中的句子进行句式结构变换。

    使用预定义的正则模板识别常见 AI 写作句式，替换为更自然的表达。
    每个句子最多匹配一个模板，避免多次改写导致语法错误。

    Args:
        text: 输入中文文本
        strength: 变换概率 (0-1)，默认 0.6 表示匹配到的句子有 60% 概率被改写

    Returns:
        改写后的文本
    """
    # 按句号/感叹号/问号切分
    parts = re.split(r'([。！？])', text)
    result = []

    for i in range(0, len(parts)):
        segment = parts[i]
        # 跳过标点本身
        if re.fullmatch(r'[。！？]', segment):
            result.append(segment)
            continue

        # 对每个句段尝试匹配模板（最多改一次）
        transformed = False
        cn_len = len(re.findall(r'[\u4e00-\u9fff]', segment))
        if segment.strip() and cn_len >= 10 and random.random() < strength:
            for pattern, replacements in _SENTENCE_TEMPLATES:
                m = pattern.search(segment)
                if m:
                    repl_fn = random.choice(replacements)
                    try:
                        new_segment = segment[:m.start()] + repl_fn(m) + segment[m.end():]
                        new_cn_len = len(re.findall(r'[\u4e00-\u9fff]', new_segment))
                        # 校验：改写后长度不应偏差太大，且不为空
                        if (len(new_segment.strip()) >= 4 and 
                            abs(new_cn_len - cn_len) < cn_len * 0.5):
                            segment = new_segment
                            transformed = True
                    except Exception:
                        pass  # 保守——出错就不改
                    break  # 一个句子最多匹配一个模板

        result.append(segment)

    return ''.join(result)


# ═══════════════════════════════════════════════════════════════════
#  2. 句子拆合
# ═══════════════════════════════════════════════════════════════════

def split_long_sentences(text):
    """在特定连接词处拆分长句为两个短句。

    拆分规则：
    - 在「不仅...还/也」处拆分
    - 在「，同时/并且/而且」处拆分
    - 在「，从而/进而」处拆分

    仅对较长的句子生效（中文字符 > 25），避免过度拆分。

    Args:
        text: 输入中文文本

    Returns:
        拆分后的文本
    """
    parts = re.split(r'([。！？])', text)
    result = []

    for i in range(len(parts)):
        segment = parts[i]
        if re.fullmatch(r'[。！？]', segment):
            result.append(segment)
            continue

        cn_len = len(re.findall(r'[\u4e00-\u9fff]', segment))
        if cn_len < 25:
            result.append(segment)
            continue

        # 尝试在"不仅...还/也"处拆分
        m = re.search(r'(?P<before>.+?)不仅(?P<A>[^，,。]{2,25})[，,]\s*(?:还|也|更)(?P<B>.+)', segment)
        if m and random.random() < 0.5:
            subj = m.group('before').strip()
            result.append(f'{subj}不仅{m.group("A")}。{subj}{m.group("B").strip()}')
            continue

        # 尝试在"，同时/并且/而且"处拆分
        m = re.search(r'(?P<before>.+?)[，,]\s*(?:同时|并且|而且)(?P<after>.+)', segment)
        if m and cn_len > 30 and random.random() < 0.4:
            result.append(f'{m.group("before").strip()}。{m.group("after").strip()}')
            continue

        # 尝试在"，从而/进而"处拆分
        m = re.search(r'(?P<before>.+?)[，,]\s*(?:从而|进而)(?P<after>.+)', segment)
        if m and cn_len > 30 and random.random() < 0.4:
            result.append(f'{m.group("before").strip()}。这样一来，{m.group("after").strip()}')
            continue

        result.append(segment)

    return ''.join(result)


def merge_short_sentences(text):
    """合并共享主语的连续短句。

    规则：
    - 如果连续两个句子共享主语（前 2-6 个字相同），合并为一个句子
    - 仅对较短的句子生效（中文字符 < 20），避免合出超长句

    Args:
        text: 输入中文文本

    Returns:
        合并后的文本
    """
    parts = re.split(r'([。])', text)
    if len(parts) < 5:  # 至少需要 2 个完整句子
        return text

    # 组装 (sentence, punctuation) 对
    sentences = []
    for i in range(0, len(parts) - 1, 2):
        s = parts[i].strip()
        p = parts[i + 1] if i + 1 < len(parts) else ''
        if s:
            sentences.append((s, p))
    if len(parts) % 2 == 1 and parts[-1].strip():
        sentences.append((parts[-1].strip(), ''))

    if len(sentences) < 2:
        return text

    result = []
    i = 0
    while i < len(sentences):
        if i + 1 < len(sentences):
            s1, p1 = sentences[i]
            s2, p2 = sentences[i + 1]

            cn1 = len(re.findall(r'[\u4e00-\u9fff]', s1))
            cn2 = len(re.findall(r'[\u4e00-\u9fff]', s2))

            # 两个都比较短，且共享前缀（主语）
            if cn1 < 20 and cn2 < 20 and cn1 + cn2 < 45:
                # 提取共享主语（2-6 个中文字）
                shared = _find_shared_subject(s1, s2)
                if shared and random.random() < 0.4:
                    # 去掉第二句的主语
                    s2_trimmed = s2[len(shared):].lstrip('，,也还更')
                    if s2_trimmed and len(s2_trimmed) > 2:
                        merged = f'{s1}，也{s2_trimmed}'
                        result.append(merged + p2)
                        i += 2
                        continue

        s, p = sentences[i]
        result.append(s + p)
        i += 1

    return ''.join(result)


def _find_shared_subject(s1, s2):
    """找出两个句子共享的主语前缀（2-6 个中文字符）。

    Args:
        s1: 第一个句子
        s2: 第二个句子

    Returns:
        共享前缀字符串，或 None
    """
    # 提取开头的中文字符序列
    m1 = re.match(r'([\u4e00-\u9fff]{2,6})', s1.strip())
    m2 = re.match(r'([\u4e00-\u9fff]{2,6})', s2.strip())
    if not m1 or not m2:
        return None

    prefix1 = m1.group(1)
    prefix2 = m2.group(1)

    # 找最长公共前缀
    shared = ''
    for c1, c2 in zip(prefix1, prefix2):
        if c1 == c2:
            shared += c1
        else:
            break

    return shared if len(shared) >= 2 else None


# ═══════════════════════════════════════════════════════════════════
#  3. 信息重排
# ═══════════════════════════════════════════════════════════════════

def reorder_mid_sentences(text):
    """在段落内部对中间句子做小幅位置调整。

    规则：
    - 如果一段有 4+ 个句子，随机交换中间 2 个句子的位置
    - 保留首句和尾句不动
    - 每段最多交换一次

    Args:
        text: 输入中文文本

    Returns:
        重排后的文本
    """
    paragraphs = text.split('\n\n')
    if not paragraphs:
        return text

    result = []
    for para in paragraphs:
        if not para.strip():
            result.append(para)
            continue

        # 切分句子
        parts = re.split(r'([。！？])', para)
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            s = parts[i]
            p = parts[i + 1] if i + 1 < len(parts) else ''
            if s.strip():
                sentences.append(s + p)
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1])

        # 4+ 句子时交换中间两个
        if len(sentences) >= 4 and random.random() < 0.5:
            mid_indices = list(range(1, len(sentences) - 1))
            if len(mid_indices) >= 2:
                i1, i2 = random.sample(mid_indices, 2)
                sentences[i1], sentences[i2] = sentences[i2], sentences[i1]

        result.append(''.join(sentences))

    return '\n\n'.join(result)


# ═══════════════════════════════════════════════════════════════════
#  4. AI 废话连接词删除
# ═══════════════════════════════════════════════════════════════════

# 已知的 AI 废话连接词/短语
_AI_FILLER_PHRASES = [
    '综上所述', '值得注意的是', '不难发现', '总而言之',
    '不可否认', '毫无疑问', '显而易见', '众所周知',
    '由此可见', '需要指出的是', '值得一提的是', '不言而喻',
    '毋庸置疑', '事实上', '实际上', '严格来说',
    '换句话说', '从某种意义上说', '在一定程度上',
    '就目前来看', '总的来说', '概括来说', '归根结底',
]


def remove_ai_fillers(text, delete_prob=0.5):
    """以一定概率直接删除已知的 AI 废话连接词。

    与同义替换不同，这里是直接删除（而非换一个说法），
    因为这些连接词本身往往是多余的，去掉后句子依然通顺。

    Args:
        text: 输入中文文本
        delete_prob: 删除概率 (0-1)，默认 0.5

    Returns:
        清理后的文本
    """
    for phrase in _AI_FILLER_PHRASES:
        # 匹配 "废话，" 或 "废话。" 开头的模式
        # 例如 "综上所述，" → 删除整个前缀
        pattern = re.escape(phrase) + r'[，,]\s*'
        matches = list(re.finditer(pattern, text))
        for m in reversed(matches):  # 从后往前删，避免位移
            if random.random() < delete_prob:
                text = text[:m.start()] + text[m.end():]

    return text


# ═══════════════════════════════════════════════════════════════════
#  主入口：深度改写
# ═══════════════════════════════════════════════════════════════════

def deep_restructure(text, aggressive=False):
    """对中文文本进行深度句级改写。

    按顺序执行：
    1. 句式结构变换（正则模板匹配）
    2. 长句拆分
    3. 短句合并
    4. AI 废话删除
    5. 段落内信息重排

    Args:
        text: 输入中文文本
        aggressive: 激进模式——更高的变换概率

    Returns:
        深度改写后的文本
    """
    strength = 0.6 if aggressive else 0.4
    delete_prob = 0.6 if aggressive else 0.35

    # 1. 句式结构变换
    text = restructure_sentences(text, strength=strength)

    # 2. 长句拆分
    text = split_long_sentences(text)

    # 3. 短句合并
    text = merge_short_sentences(text)

    # 4. AI 废话删除
    text = remove_ai_fillers(text, delete_prob=delete_prob)

    # 5. 信息重排（仅对多段落文本生效）
    if '\n\n' in text:
        text = reorder_mid_sentences(text)

    # 清理可能产生的标点问题
    text = re.sub(r'[，,]{2,}', '，', text)
    text = re.sub(r'[。]{2,}', '。', text)
    text = re.sub(r'，。', '。', text)
    text = re.sub(r'。，', '。', text)
    text = re.sub(r'^\s*[，,]', '', text)  # 句首逗号

    return text
