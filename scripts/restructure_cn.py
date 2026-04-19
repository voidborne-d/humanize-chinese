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

    # ── 16. X对Y产生了重要影响 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})对(?P<Y>[^，,。]{2,12})产生了(?:重要|深远|显著|明显)?影响'),
        [
            lambda m: f'{m.group("X")}对{m.group("Y")}的影响不容忽视',
            lambda m: f'{m.group("Y")}受到{m.group("X")}的牵动',
        ]
    ))

    # ── 17. 可以看出/可见，X ──
    templates.append((
        re.compile(r'(?:可以看出|可见|不难看出|显而易见)[，,]\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'从中可以看出，{m.group("X")}',
            lambda m: f'大致上可以看出，{m.group("X")}',
        ]
    ))

    # ── 18. 通过对X的分析/研究 ──
    templates.append((
        re.compile(r'通过对(?P<X>[^，,。]{2,15})的(?:分析|研究|考察|探讨)[，,]\s*(?P<Y>[^。！？]{5,40})'),
        [
            lambda m: f'对{m.group("X")}加以分析后，{m.group("Y")}',
            lambda m: f'围绕{m.group("X")}展开分析，{m.group("Y")}',
        ]
    ))

    # ── 19. X主要体现在Y ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})主要体现在(?P<Y>[^。！？]{2,30})'),
        [
            lambda m: f'{m.group("X")}集中表现为{m.group("Y")}',
            lambda m: f'{m.group("X")}的表征在于{m.group("Y")}',
        ]
    ))

    # ── 20. X有助于Y的实现/提升 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})有助于(?P<Y>[^，,。]{2,20})的(?:实现|提升|改善|促进|推动)'),
        [
            lambda m: f'{m.group("X")}有利于{m.group("Y")}',
            lambda m: f'{m.group("X")}对{m.group("Y")}的达成有所促进',
        ]
    ))

    # ── 21. X成为Y的重要/关键手段 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})成为(?P<Y>[^，,。]{2,12})的(?:重要|关键|主要)(?P<Z>手段|方式|途径|方法|工具)'),
        [
            lambda m: f'{m.group("X")}是{m.group("Y")}的要紧{m.group("Z")}',
            lambda m: f'{m.group("X")}作为{m.group("Y")}的关键{m.group("Z")}',
        ]
    ))

    # ── 22. X呈现出Y的趋势/特点 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})呈现出(?P<Y>[^，,。]{2,15})的(?P<Z>趋势|特点|态势|特征)'),
        [
            lambda m: f'{m.group("X")}渐现{m.group("Y")}的{m.group("Z")}',
            lambda m: f'{m.group("X")}显出{m.group("Y")}的{m.group("Z")}',
        ]
    ))

    # ── 23. X受到Y的影响/制约 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})受到(?P<Y>[^，,。]{2,12})的(?:影响|制约|限制|驱动)'),
        [
            lambda m: f'{m.group("Y")}对{m.group("X")}有其作用',
            lambda m: f'{m.group("X")}因{m.group("Y")}而变动',
        ]
    ))

    # ── 24. X为Y奠定/打下了基础 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})为(?P<Y>[^，,。]{2,12})(?:奠定|打下)了(?:坚实|重要|良好)?基础'),
        [
            lambda m: f'{m.group("X")}给{m.group("Y")}打下了基础',
            lambda m: f'有了{m.group("X")}，{m.group("Y")}才有开端',
        ]
    ))

    # ── 25. X离不开Y ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})离不开(?P<Y>[^，,。]{2,20})'),
        [
            lambda m: f'{m.group("X")}少不了{m.group("Y")}',
            lambda m: f'没有{m.group("Y")}，{m.group("X")}便难以成立',
        ]
    ))

    # ── 26. X起到了重要/关键作用 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})起到了(?:重要|关键|核心|积极)(?P<Y>作用|影响|意义)'),
        [
            lambda m: f'{m.group("X")}起了要紧的{m.group("Y")}',
            lambda m: f'在这里，{m.group("X")}的{m.group("Y")}不小',
        ]
    ))

    # ── 27. 可以预见，X ──
    templates.append((
        re.compile(r'(?:可以预见|不难预见|可以预期)[，,]\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'大致可以预计，{m.group("X")}',
            lambda m: f'由此不难推断，{m.group("X")}',
        ]
    ))

    # ── 28. 值得关注的是X ──
    templates.append((
        re.compile(r'值得(?:关注|注意|留意|重视)的是[，,]\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'{m.group("X")}值得留意',
            lambda m: f'有一点值得一提，{m.group("X")}',
        ]
    ))

    # ── 29. 从X来看/角度看 ──
    templates.append((
        re.compile(r'从(?P<X>[^，,。]{2,15})(?:来看|的角度看|的视角看)[，,]\s*(?P<Y>[^。！？]{5,40})'),
        [
            lambda m: f'就{m.group("X")}而言，{m.group("Y")}',
            lambda m: f'{m.group("X")}的层面上，{m.group("Y")}',
        ]
    ))

    # ── 30. 这一现象/结果反映出X ──
    templates.append((
        re.compile(r'这一?(?:现象|结果|情况|趋势)反映出(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'这种情况照出{m.group("X")}',
            lambda m: f'由此可以看出{m.group("X")}',
        ]
    ))

    # ── 31. 这说明/表明/意味着X ──
    templates.append((
        re.compile(r'这(?:说明|表明|意味着|反映)(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'也就是说，{m.group("X")}',
            lambda m: f'此即{m.group("X")}',
        ]
    ))

    # ── 32. X已经成为Y ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})已(?:经)?成为(?P<Y>[^。！？]{2,25})'),
        [
            lambda m: f'{m.group("X")}如今是{m.group("Y")}',
            lambda m: f'{m.group("X")}现在已是{m.group("Y")}',
        ]
    ))

    # ── 33. X越来越Y ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})越来越(?P<Y>[^，,。]{1,10})'),
        [
            lambda m: f'{m.group("X")}日渐{m.group("Y")}',
            lambda m: f'{m.group("X")}愈加{m.group("Y")}',
        ]
    ))

    # ── 34. X与Y密切相关 / X与Y的关系 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,12})(?:与|和)(?P<Y>[^，,。]{2,12})密切相关'),
        [
            lambda m: f'{m.group("X")}和{m.group("Y")}关系密切',
            lambda m: f'{m.group("X")}跟{m.group("Y")}紧密相连',
        ]
    ))

    # ── 35. X需要Y ──（仅在句首或主语明确时）
    templates.append((
        re.compile(r'^(?P<X>[\u4e00-\u9fff]{2,10})需要(?P<Y>[^。！？]{2,30})'),
        [
            lambda m: f'{m.group("X")}少不了{m.group("Y")}',
            lambda m: f'{m.group("X")}得{m.group("Y")}',
        ]
    ))

    # ── 36. X的重要性不容忽视 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})的(?:重要性|意义|价值|作用)不容忽视'),
        [
            lambda m: f'{m.group("X")}不容忽视',
            lambda m: f'{m.group("X")}不可小觑',
        ]
    ))

    # ── 37. X将带来/产生Y ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})将(?:带来|产生|引发|催生)(?P<Y>[^。！？]{2,25})'),
        [
            lambda m: f'{m.group("X")}会带来{m.group("Y")}',
            lambda m: f'{m.group("X")}可能引出{m.group("Y")}',
        ]
    ))

    # ── 38. 根据X，Y ──
    templates.append((
        re.compile(r'^根据(?P<X>[^，,。]{2,15})[，,]\s*(?P<Y>[^。！？]{5,40})'),
        [
            lambda m: f'按{m.group("X")}来看，{m.group("Y")}',
            lambda m: f'依{m.group("X")}，{m.group("Y")}',
        ]
    ))

    # ── 39. X具有广阔的Y前景/空间 ──
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})具有(?:广阔|广泛|巨大|显著)的(?P<Y>[^，,。]{1,6})(?:前景|空间|潜力|价值)'),
        [
            lambda m: f'{m.group("X")}在{m.group("Y")}上大有可为',
            lambda m: f'{m.group("X")}的{m.group("Y")}潜力仍待挖掘',
        ]
    ))

    # ── 40. 不仅如此，X ──
    templates.append((
        re.compile(r'^不仅如此[，,]\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'此外，{m.group("X")}',
            lambda m: f'还有一点，{m.group("X")}',
        ]
    ))

    # ── 41. 在X的Y下，Z（背景/情况/影响/指导/推动）── D-2 / cycle 42
    templates.append((
        re.compile(r'在(?P<X>[^，,。]{2,15})的(?P<Y>背景|情况|影响|指导|推动|框架)下[，,]\s*(?P<Z>[^。！？]{5,40})'),
        [
            lambda m: f'{m.group("X")}的{m.group("Y")}下，{m.group("Z")}',
            lambda m: f'{m.group("Z")}——这正是{m.group("X")}的{m.group("Y")}造成的',
        ]
    ))

    # ── 42. 研究表明/研究发现 X ── D-2 / cycle 42
    templates.append((
        re.compile(r'^(?:研究|数据|调查|分析)(?:表明|显示|发现|揭示|指出)[，,]?\s*(?P<X>[^。！？]{5,40})'),
        [
            lambda m: f'有研究显示，{m.group("X")}',
            lambda m: f'实际数据里，{m.group("X")}',
        ]
    ))

    # ── 43. X取决于Y ── D-2 / cycle 42（HC3-mined 高频）
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,20})取决于(?P<Y>[^。！？]{2,25})'),
        [
            lambda m: f'{m.group("X")}要看{m.group("Y")}',
            lambda m: f'{m.group("X")}跟{m.group("Y")}有关',
        ]
    ))

    # ── 44. X将/已经成为Y ── D-2 / cycle 42
    templates.append((
        re.compile(r'(?P<X>[^，,。]{2,15})(?:将|已经|正在|逐渐)成为(?P<Y>[^。！？]{2,25})'),
        [
            lambda m: f'{m.group("X")}正转变为{m.group("Y")}',
            lambda m: f'{m.group("X")}这条路，通向{m.group("Y")}',
        ]
    ))

    # ── 45. 通过对X的Y，Z（academic analysis 套路）── D-2 / cycle 42
    templates.append((
        re.compile(r'^通过对(?P<X>[^，,。]{2,20})的(?P<Y>分析|研究|探讨|考察|梳理)[，,]\s*(?P<Z>[^。！？]{5,40})'),
        [
            lambda m: f'梳理{m.group("X")}后发现，{m.group("Z")}',
            lambda m: f'把{m.group("X")}{m.group("Y")}一番，{m.group("Z")}',
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
        # before 必须是短的无内部逗号的主语（2-10 中文字），否则拆分会把整段复制。
        # 例：避免 "智能评估系统能够多维度地评判学生的综合素质，不仅..." 被当作 before 整段复制。
        m = re.search(r'(?P<before>[\u4e00-\u9fff]{2,10})不仅(?P<A>[^，,。]{2,25})[，,]\s*(?:还|也|更)(?P<B>.+)', segment)
        if m and random.random() < 0.5:
            # 确认 match 起始就是 before（即 before 前面没有其它句子内容，是真正的主语位）
            if m.start() == 0 or segment[m.start() - 1] in '，。！？':
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
    - 按段落 (\\n\\n) 分别处理，避免吃掉段落分隔符

    Args:
        text: 输入中文文本

    Returns:
        合并后的文本
    """
    # 按段落切分处理，避免 .strip() 吃掉 \n\n
    paragraphs = text.split('\n\n')
    return '\n\n'.join(_merge_short_sentences_in_paragraph(p) for p in paragraphs)


def _merge_short_sentences_in_paragraph(text):
    """在单个段落内合并短句。调用方负责段落切分。"""
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

    # D-7 (cycle 33): don't merge if paragraph already has natural short-sentence
    # variety — merging destroys the human short_frac signature and triggers
    # low_short_sentence_fraction + low_sentence_length_cv indicators.
    # Found via HC3 regression diagnosis: sample #90 regressed +15 because
    # humanize merged away natural short sentences.
    cn_lens = [len(re.findall(r'[\u4e00-\u9fff]', s)) for s, _ in sentences]
    if cn_lens:
        short_frac = sum(1 for l in cn_lens if l < 10) / len(cn_lens)
        if short_frac >= 0.20:  # text already human-like burstiness
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
        # 只吃水平空白（空格/tab），不吃 \n，否则会吃掉段落分隔符
        pattern = re.escape(phrase) + r'[，,][ \t]*'
        matches = list(re.finditer(pattern, text))
        for m in reversed(matches):  # 从后往前删，避免位移
            if random.random() < delete_prob:
                text = text[:m.start()] + text[m.end():]

    return text


# ═══════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
#  Short-sentence insertion (句长 humanize side, cycle 6 alternative approach)
# ═══════════════════════════════════════════════════════════════════
#
# Cycle 5 detect added `low_short_sentence_fraction` indicator (HC3 d=1.21 —
# AI writes < 3% short sentences vs humans' 25%). Cycle 6 tried to split long
# sentences at commas and failed (orphan predicates). This alternative inserts
# short reaction phrases at paragraph seams — safer because we're adding complete
# sentences rather than severing them.
#
# The reaction phrases are deliberately NEUTRAL (not "综上所述/首先/然而" which
# are AI fillers) and short (3-6 chars) so they count toward short_frac.

_SHORT_REACTIONS_NEUTRAL = [
    # D-3 cycle 29: dropped 2-char "的确" — sentence-length feature skips < 3
    # Chinese chars so 2-char reactions don't register as "short sentences".
    # All entries now 4-6 chars, each reaction registers properly.
    '确实如此。', '颇有道理。', '不无道理。',
    '事出有因。', '耐人寻味。', '值得深思。', '让人深思。',
    '可见一斑。', '有一定道理。', '各有道理。', '各有说法。',
    '难以一概。', '难以断言。', '说来话长。', '一言难尽。',
    '的确如此。', '确实是这样。',
]

_SHORT_REACTIONS_CASUAL = [
    '真是这样。', '我这么认为。', '我觉得吧。', '可能吧。',
    '大概是这样。', '应该差不多。', '是这个理。', '有道理。',
]


# Comma-insertion markers — keys where inserting a comma before them is
# grammatically safe in Chinese. Ordered by preference (most natural first).
# Caveat: only insert if the clause BEFORE the marker is 8+ Chinese chars
# with no existing comma.
_COMMA_BEFORE_MARKERS = (
    # Copula + noun
    '是一种', '是一项', '是一个', '是我们', '是可以',
    '是提升', '是提高', '是促进', '是加强', '是时间', '是一类',
    # Modal / aux
    '能够', '可以', '具有', '需要', '将会', '已经',
    '逐步', '一直', '正在', '不仅', '而且',
    '有着', '才能', '因而',
    # V + le — common academic verb-past pattern (E-3)
    '丰富了', '提供了', '引起了', '提升了', '奠定了',
    '创造了', '推动了', '产生了', '揭示了', '展现了',
    '带来了', '形成了', '构建了', '拓展了', '优化了',
    '提出了', '收到了', '达到了', '实现了', '促进了',
    # V + chu — aspectual (E-3)
    '呈现出', '显现出', '表现出', '表达出',
    # V + zhe — continuous action (E-3)
    '扮演着', '发挥着', '起着', '承担着', '承载着',
    # Attribution style (softer than splitting)
    '表明', '揭示', '显示', '发现', '证实', '体现',
)


def boost_comma_density(text, target=4.7):
    """Insert commas at safe natural-pause points when density is below target.

    HC3 calibration: humans median 5.30/100 chars, AI 3.81. detect_cn flags
    < 4.5. Restructuring sometimes leaves density below threshold — this
    function adds commas at grammatically safe spots to compensate.

    Strategy: scan sentences; for each sentence >= 15 Chinese chars with
    at most 1 existing comma, find a natural pause marker in the middle
    (6+ chars from start) and insert a comma before it. Only processes
    as many sentences as needed to clear the threshold.

    Args:
        text: input text (already passed through other restructure steps)
        target: target density per 100 non-whitespace chars (default 4.7)

    Returns:
        text with 0+ commas added
    """
    non_ws = sum(1 for c in text if not c.isspace())
    if non_ws < 100:
        return text
    commas = text.count('，') + text.count(',')
    current = commas / non_ws * 100
    if current >= target:
        return text
    # How many commas do we need to reach target?
    needed = int((target - current) * non_ws / 100) + 1

    # Walk through sentences; for each eligible long clause, insert one comma
    # at the first safe marker position.
    pieces = re.split(r'([。！？\n]+)', text)
    out = []
    added = 0
    for piece in pieces:
        if added >= needed or not piece or piece[0] in '。！？\n':
            out.append(piece)
            continue
        sent = piece
        # Count Chinese chars and existing commas in this sentence
        cn_chars = sum(1 for c in sent if '\u4e00' <= c <= '\u9fff')
        if cn_chars < 15 or sent.count('，') + sent.count(',') >= 2:
            out.append(piece)
            continue
        # Find first safe marker at position >= 6 Chinese chars from start
        # (and with no comma before it already)
        best_pos = -1
        for marker in _COMMA_BEFORE_MARKERS:
            idx = sent.find(marker)
            if idx <= 0:
                continue
            # Count Chinese chars before this idx
            prefix = sent[:idx]
            prefix_cn = sum(1 for c in prefix if '\u4e00' <= c <= '\u9fff')
            if prefix_cn < 6:
                continue
            # No comma in the last 6 chars before marker (avoid double-comma-tight)
            tail_prefix = prefix[-6:] if len(prefix) > 6 else prefix
            if '，' in tail_prefix or ',' in tail_prefix:
                continue
            # Don't insert at very end either (need some stuff after)
            suffix_cn = sum(1 for c in sent[idx:] if '\u4e00' <= c <= '\u9fff')
            if suffix_cn < 4:
                continue
            best_pos = idx
            break
        if best_pos > 0:
            sent = sent[:best_pos] + '，' + sent[best_pos:]
            added += 1
        out.append(sent)
    return ''.join(out)


def insert_short_reactions(text, target_short_frac=0.15, max_per_paragraph=1, seed=None, min_sentences=3, scene='general'):
    """Inject short reaction sentences at paragraph seams where short_frac is low.

    Only injects when:
      - paragraph has at least 3 sentences
      - current short-sentence fraction (< 10 chars) is below target
      - at least one sentence is > 20 chars (good anchor for the insertion)

    Args:
        text: input text (paragraphs split by \\n\\n)
        target_short_frac: stop inserting once short_frac reaches this
        max_per_paragraph: hard cap on insertions per paragraph
        seed: pass to seed random choice (caller-managed usually)

    Returns:
        text with 0 or more short reactions inserted
    """
    if seed is not None:
        random.seed(seed)
    paragraphs = text.split('\n\n')
    return '\n\n'.join(
        _insert_reactions_in_paragraph(p, target_short_frac, max_per_paragraph, min_sentences, scene)
        for p in paragraphs
    )


def _insert_reactions_in_paragraph(p, target, max_per, min_sentences=3, scene='general'):
    parts = re.split(r'([。！？])', p)
    sentences = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and parts[i + 1] in '。！？':
            if seg.strip():
                sentences.append(seg + parts[i + 1])
            i += 2
        else:
            if seg.strip():
                sentences.append(seg)
            i += 1

    if len(sentences) < min_sentences:
        return p

    cn_lens = [sum(1 for c in s if '\u4e00' <= c <= '\u9fff') for s in sentences]
    if not cn_lens:
        return p
    current_short_frac = sum(1 for l in cn_lens if l < 10) / len(cn_lens)
    if current_short_frac >= target:
        return p

    # Only insert at paragraph END (last position) — mid-paragraph insertion
    # disrupts academic flow and breaks list/argument continuity.
    last_idx = len(sentences) - 1
    if cn_lens[last_idx] < 15:
        return p  # last sentence is already short; don't pile on

    # For non-social scenes, use adaptive probability: larger gap to target
    # → more likely to insert. Social scene keeps fixed low prob to avoid
    # disrupting downstream style transforms (xhs hashtags/emojis dilute
    # comma density when extra reactions pile up — cycle 37).
    if scene == 'social':
        prob = 0.35
    else:
        gap = max(0.0, target - current_short_frac)
        prob = min(0.85, 0.35 + gap * 3.0)
    if random.random() < prob:
        reaction = random.choice(_SHORT_REACTIONS_NEUTRAL)
        sentences.append(reaction)

    return ''.join(sentences)


# ═══════════════════════════════════════════════════════════════════
#  句长多样化（针对句长 burstiness 检测器）
# ═══════════════════════════════════════════════════════════════════

def diversify_sentence_lengths(text, target_cv=0.42, target_short_frac=0.10):
    """Split long sentences at commas to boost sentence-length CV.

    HC3 300+300 calibration shows AI Chinese text has sentence-length CV ~0.32
    and short-sentence (<10 char) fraction ~2.6%, vs human CV ~0.52 and
    short-fraction ~25%. Our detect_cn flags text with CV < 0.40 or short_frac < 8%.

    This function splits any sentence > 30 Chinese chars at the comma nearest to
    its midpoint, repeating until CV >= target_cv and short_frac >= target_short_frac
    (or no more splittable sentences remain). Paragraph-aware via \\n\\n.

    Args:
        text: input text
        target_cv: stop once CV reaches this
        target_short_frac: stop once fraction of <10-char sentences reaches this

    Returns:
        text with more varied sentence lengths
    """
    paragraphs = text.split('\n\n')
    return '\n\n'.join(
        _diversify_in_paragraph(p, target_cv, target_short_frac)
        for p in paragraphs
    )


# Attribution verbs — splitting after these breaks Chinese grammar.
# e.g., "李某某指出，X" → "李某某指出。X" is ungrammatical.
_ATTRIBUTION_SUFFIXES = (
    '指出', '表明', '揭示', '发现', '显示', '提出', '认为', '指向', '表示',
    '说明', '声称', '强调', '声明', '注意到', '称', '讲', '说', '提及',
    '反映', '暗示', '宣称', '阐述', '论证', '主张', '建议', '呼吁',
    '写道', '记录', '陈述', '描述', '证明', '表达',
)

# Subordinate-clause leads — don't split right after these, the comma belongs to
# the subordinate marker and splitting strands the main clause.
_SUBORDINATE_PREFIXES = (
    '随着', '鉴于', '为了', '由于', '尽管', '虽然', '如果', '倘若', '假如',
    '只要', '只有', '除非', '一旦', '既然', '即使', '不管', '无论', '因为',
    '自从', '每当', '当', '若', '假使',
)


def _split_sentence_at_comma(segment):
    """Split a long sentence at the comma nearest its middle.

    Skips commas that would strand an attribution verb or cut inside a
    subordinate clause (e.g. 随着…，X → 随着。X is ungrammatical).

    Returns (left, right) both as Chinese-punctuation-terminated, or None if
    no suitable split point exists.
    """
    cn_len = len(re.findall(r'[\u4e00-\u9fff]', segment))
    if cn_len < 40:
        return None

    # Trailing terminator (preserve on right half)
    term_match = re.search(r'[。！？]$', segment)
    terminator = term_match.group() if term_match else '。'
    body = segment[:term_match.start()] if term_match else segment

    commas = [i for i, c in enumerate(body) if c in '，,']
    # Require >= 3 commas — gives us confidence the sentence has real clause
    # structure, so cutting at one comma leaves each half with its own commas
    # (real sub-clauses) rather than stranding a bare predicate phrase.
    if len(commas) < 3:
        return None

    body_stripped_start = body.lstrip()
    starts_with_subordinate = any(
        body_stripped_start.startswith(p) for p in _SUBORDINATE_PREFIXES
    )

    # Try commas nearest midpoint first, skipping unsafe ones
    midpoint = len(body) // 2
    commas_by_distance = sorted(commas, key=lambda i: abs(i - midpoint))

    for best in commas_by_distance:
        left_tail = body[:best]
        right_head = body[best + 1:].strip()

        # Guard 1: don't strand an attribution verb
        if any(left_tail.rstrip().endswith(v) for v in _ATTRIBUTION_SUFFIXES):
            continue

        # Guard 2: subordinate clause — first comma after a 随着/鉴于/etc marker
        # is the clause boundary; splitting there breaks the sentence
        if starts_with_subordinate:
            # If this is the FIRST comma in the sentence, it's likely the subordinate marker's
            # closing comma — splitting here gives us a bare subordinate clause on the left
            if best == commas[0]:
                continue

        left = left_tail.strip()
        right = right_head

        left_cn = len(re.findall(r'[\u4e00-\u9fff]', left))
        right_cn = len(re.findall(r'[\u4e00-\u9fff]', right))
        if left_cn < 4 or right_cn < 4:
            continue

        return left + '。', right + terminator

    return None


def _sentence_length_stats(sentences):
    """Compute (cv, short_frac) for a list of sentence strings."""
    lens = []
    for s in sentences:
        cn = len(re.findall(r'[\u4e00-\u9fff]', s))
        if cn >= 3:
            lens.append(cn)
    if len(lens) < 3:
        return 1.0, 1.0  # treat as "already diverse" (too few to judge)
    mean = sum(lens) / len(lens)
    if mean == 0:
        return 1.0, 1.0
    variance = sum((x - mean) ** 2 for x in lens) / len(lens)
    cv = (variance ** 0.5) / mean
    short_frac = sum(1 for x in lens if x < 10) / len(lens)
    return cv, short_frac


def _diversify_in_paragraph(text, target_cv, target_short_frac):
    """Split long sentences in a single paragraph until targets met."""
    parts = re.split(r'([。！？])', text)
    sentences = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and parts[i + 1] in '。！？':
            sentences.append(seg + parts[i + 1])
            i += 2
        else:
            if seg.strip():
                sentences.append(seg)
            i += 1

    if len(sentences) < 2:
        return text

    # Iteratively split the longest sentence until targets reached or no split possible
    MAX_ITERATIONS = 3
    for _ in range(MAX_ITERATIONS):
        cv, short_frac = _sentence_length_stats(sentences)
        if cv >= target_cv and short_frac >= target_short_frac:
            break

        # Find longest splittable sentence
        candidates = []
        for idx, s in enumerate(sentences):
            cn = len(re.findall(r'[\u4e00-\u9fff]', s))
            comma_count = sum(1 for c in s if c in '，,')
            if cn >= 40 and comma_count >= 3:
                candidates.append((cn, idx))
        if not candidates:
            break
        candidates.sort(reverse=True)
        _, idx = candidates[0]
        split_result = _split_sentence_at_comma(sentences[idx])
        if not split_result:
            break
        left, right = split_result
        sentences[idx:idx + 1] = [left, right]

    return ''.join(sentences)


# ═══════════════════════════════════════════════════════════════════
#  主入口：深度改写
# ═══════════════════════════════════════════════════════════════════

def deep_restructure(text, aggressive=False, scene='general'):
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
        scene: passed for future use; currently insert threshold stays at 3 for
               all scenes (D-3 scene-aware attempt at cycle 29 regressed
               general +2 / xhs +6 via indirect score paths)

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

    # 4b. 短句插入 — MUST run AFTER merge_short_sentences (cycle 22 bug fix).
    text = insert_short_reactions(text, scene=scene)

    # 4c. 逗号密度补足 — HC3 calibration: human 5.30 median vs AI 3.81 (d=-0.47).
    # detect_cn threshold 4.5, human mean 5.30. Target 5.0 gives headroom for
    # downstream xhs/style transforms that dilute density by adding non-comma
    # chars (emojis, symbols). Cycle 35 (E-2), retuned cycle 37 (E-4).
    text = boost_comma_density(text, target=5.0)

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
