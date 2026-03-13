#!/usr/bin/env python3
"""
Chinese Text Style Transformer v2.0
将文本转换为不同的中文写作风格
支持：口语化、知乎、小红书、公众号、学术、文艺、微博
"""

import sys
import re
import random
import argparse

# ─── 风格配置 ───

STYLES = {
    'casual': {
        'name': '口语化风格',
        'description': '像朋友聊天，适合社交媒体',
    },
    'zhihu': {
        'name': '知乎风格',
        'description': '理性、有深度、带个人观点',
    },
    'xiaohongshu': {
        'name': '小红书风格',
        'description': '活泼、emoji多、种草感',
    },
    'wechat': {
        'name': '公众号风格',
        'description': '有故事感、引人入胜',
    },
    'academic': {
        'name': '学术风格',
        'description': '严谨但不死板',
    },
    'literary': {
        'name': '文艺风格',
        'description': '有文学感、意境',
    },
    'weibo': {
        'name': '微博风格',
        'description': '简短、有态度、适合传播',
    },
}

# ─── 通用工具 ───

FORMAL_TO_CASUAL = {
    '首先': '',
    '其次': '再说',
    '最后': '最后',
    '值得注意的是': '注意',
    '综上所述': '总之',
    '不难发现': '可以看到',
    '总而言之': '总的来说',
    '与此同时': '同时',
    '在此基础上': '基于这个',
    '由此可见': '所以',
    '此外': '另外',
    '然而': '但是',
    '因此': '所以',
    '并且': '而且',
    '不可否认': '确实',
    '显而易见': '明摆着',
    '不言而喻': '不用说',
    '毋庸置疑': '肯定的是',
}

EMOJIS = {
    'positive': ['😊', '👍', '❤️', '🎉', '✨', '💪', '🔥', '👏', '💯', '🌟'],
    'thinking': ['🤔', '💭', '💡', '🧐', '👀'],
    'warning': ['⚠️', '❗', '⚡'],
    'casual': ['😂', '😅', '🙃', '😎', '🥲'],
    'xhs': ['✨', '💕', '🌸', '💗', '🎀', '💫', '🌈', '💖', '🧸', '🍃'],
}

def remove_formal_structure(text):
    """移除正式三段式结构"""
    text = re.sub(r'首先[，,]\s*', '', text)
    text = re.sub(r'其次[，,]\s*', '', text)
    text = re.sub(r'最后[，,]\s*', '', text)
    text = re.sub(r'第[一二三四五六][，,、]\s*', '', text)
    text = re.sub(r'其[一二三][，,、]\s*', '', text)
    return text

def replace_formal_words(text):
    """替换正式用词为口语化"""
    for formal, casual in FORMAL_TO_CASUAL.items():
        if formal in text:
            if casual:
                text = text.replace(formal, casual)
            else:
                text = text.replace(formal + '，', '')
                text = text.replace(formal, '')
    return text

def add_emojis(text, category='positive', density=0.2):
    """在句尾添加 emoji"""
    pool = EMOJIS.get(category, EMOJIS['positive'])
    sentences = re.split(r'([。！？])', text)
    result = []
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i]
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if random.random() < density and sent.strip():
            emoji = random.choice(pool)
            result.append(sent + emoji + punct)
        else:
            result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    return ''.join(result)

def shorten_paragraphs(text, max_length=120):
    """缩短段落"""
    paragraphs = text.split('\n\n')
    result = []
    
    for para in paragraphs:
        if len(para) > max_length:
            sentences = re.split(r'([。！？])', para)
            chunks = []
            current = ''
            
            for i in range(0, len(sentences) - 1, 2):
                s = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
                if len(current) + len(s) > max_length and current:
                    chunks.append(current.strip())
                    current = s
                else:
                    current += s
            if current.strip():
                chunks.append(current.strip())
            result.extend(chunks)
        else:
            result.append(para)
    
    return '\n\n'.join(result)

def strip_emojis(text):
    """Remove all emoji characters"""
    # Comprehensive emoji regex
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended
        "\U00002600-\U000026FF"  # misc symbols
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0000200D"             # ZWJ
        "\U00002B50"             # star
        "\U00002764"             # heart
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)

# ─── 风格转换函数 ───

def transform_casual(text):
    """口语化风格"""
    text = remove_formal_structure(text)
    text = replace_formal_words(text)
    
    sentences = re.split(r'([。！？])', text)
    result = []
    
    openers_used = False
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        # 开头加口语化引导
        if not openers_used and i == 0:
            opener = random.choice(['你看', '说起来', '其实', '讲真'])
            sent = opener + '，' + sent
            openers_used = True
        
        # 随机加语气词
        if random.random() < 0.15:
            particle = random.choice(['吧', '呢', '啊', '嘛'])
            sent = sent + particle
        
        # 随机加口语连接
        if i > 0 and random.random() < 0.15:
            connector = random.choice(['不过', '话说', '说实话', '确实'])
            sent = connector + '，' + sent
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    text = ''.join(result)
    text = add_emojis(text, 'casual', density=0.1)
    return text

def transform_zhihu(text):
    """知乎风格"""
    text = remove_formal_structure(text)
    text = replace_formal_words(text)
    
    sentences = re.split(r'([。！？])', text)
    result = []
    total = len(sentences) // 2
    
    # 添加个人视角
    opinion_added = False
    example_added = False
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        # 第一句加个人标记
        if i == 0 and not opinion_added:
            marker = random.choice(['从我的经验来看', '说点个人看法', '这个问题我来聊聊'])
            sent = marker + '，' + sent
            opinion_added = True
        
        # 中间加举例
        if not example_added and i >= total // 2 and random.random() < 0.3:
            sent = '举个例子，' + sent
            example_added = True
        
        # 在某些句子前加数据/经验支撑（避免和已有连接词叠加）
        connector_words = ['总之', '另外', '还有', '所以', '但是', '不过', '同时']
        has_connector = any(sent.startswith(w) for w in connector_words)
        if not has_connector and random.random() < 0.1:
            support = random.choice(['实际上', '从数据来看', '根据实际经验'])
            sent = support + '，' + sent
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    text = ''.join(result)
    
    # 知乎结尾
    if random.random() < 0.3:
        endings = [
            '\n\n以上，希望对你有帮助。',
            '\n\n欢迎讨论。',
            '\n\n个人观点，仅供参考。',
        ]
        text += random.choice(endings)
    
    return text

def transform_xiaohongshu(text):
    """小红书风格"""
    text = remove_formal_structure(text)
    text = replace_formal_words(text)
    
    # 开头
    openers = [
        '姐妹们！今天必须分享一下',
        '天哪！终于忍不住要说了',
        '家人们谁懂啊',
        '绝了绝了！分享一个',
        '姐妹们冲！',
    ]
    
    # 处理句子
    sentences = re.split(r'([。！？])', text)
    result = []
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        # 替换中性词为种草用语
        xhs_replacements = {
            '好': random.choice(['绝了', '太好了', '爱了']),
            '推荐': random.choice(['强推', '安利', '必入']),
            '不错': random.choice(['真的绝', '超赞', 'yyds']),
        }
        for old, new in xhs_replacements.items():
            if old in sent and random.random() < 0.3:
                sent = sent.replace(old, new, 1)
        
        # 加感叹号比例
        if random.random() < 0.3:
            punct = '！'
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    text = random.choice(openers) + '～\n\n' + ''.join(result)
    
    # 加 emoji（高密度）
    text = add_emojis(text, 'xhs', density=0.4)
    
    # 短段落
    text = shorten_paragraphs(text, max_length=80)
    
    # 加话题标签
    tags = random.sample([
        '#好物分享', '#种草', '#实用推荐', '#干货分享',
        '#生活分享', '#经验分享', '#必看', '#宝藏',
    ], 3)
    text += '\n\n' + ' '.join(tags)
    
    return text

def transform_wechat(text):
    """公众号风格"""
    text = remove_formal_structure(text)
    
    # 故事化开头
    openings = [
        '你有没有想过这样一个问题——',
        '最近发生了一件有意思的事。',
        '很多人都经历过这样的困境。',
        '说一个真实的故事。',
        '前几天有个朋友问我：',
    ]
    
    if not any(text.startswith(op[:3]) for op in openings):
        text = random.choice(openings) + '\n\n' + text
    
    # 在中间插入互动性问句
    sentences = re.split(r'([。！？])', text)
    result = []
    total = len(sentences) // 2
    question_added = False
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        # 中间插反问
        if not question_added and i >= total // 3 and i <= total * 2 // 3 and random.random() < 0.4:
            questions = ['你可能会问', '为什么呢', '这意味着什么']
            result.append('\n\n' + random.choice(questions) + '？\n\n')
            question_added = True
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    text = ''.join(result)
    
    # 公众号结尾
    if random.random() < 0.4:
        endings = [
            '\n\n**如果觉得有用，欢迎点赞收藏。**',
            '\n\n你怎么看？评论区聊聊。',
            '\n\n希望这篇对你有启发。',
        ]
        text += random.choice(endings)
    
    return text

def transform_academic(text):
    """学术风格"""
    # 口语化 → 学术化
    casual_to_formal = {
        '很': '较为',
        '特别': '尤其',
        '挺': '相对',
        '蛮': '较为',
        '说实话': '',
        '确实': '',
        '讲真': '',
        '没想到': '',
        '说起来': '',
        '你看': '',
    }
    
    for casual, formal in casual_to_formal.items():
        if casual in text:
            if formal:
                text = text.replace(casual, formal)
            else:
                text = text.replace(casual + '，', '')
                text = text.replace(casual, '')
    
    # 移除 emoji
    text = strip_emojis(text)
    
    # 学术化连接词
    text = text.replace('所以，', '因此，')
    text = text.replace('但是，', '然而，')
    text = text.replace('而且，', '此外，')
    
    # 移除口语化语气词
    text = re.sub(r'[吧呢啊嘛哦哈]([。！？，])', r'\1', text)
    
    # 把 ！ 换成 。 （学术文章少用感叹号）
    exclamation_count = text.count('！')
    if exclamation_count > 2:
        # Keep at most 1 exclamation
        parts = text.split('！')
        text = '。'.join(parts[:-1]) + '。' + parts[-1] if len(parts) > 1 else text
    
    return text

def transform_literary(text):
    """文艺风格"""
    text = remove_formal_structure(text)
    text = replace_formal_words(text)
    
    # 意象词库
    imagery = {
        '开始': ['如同晨曦初现', '宛若春风拂面'],
        '结束': ['终如落日沉入海平线', '在最后的余晖中'],
        '变化': ['恰似流水无声地改变河床', '如同季节的更迭'],
        '重要': ['像一颗定海神针', '如同根基之于大厦'],
        '困难': ['像是在荆棘中寻路', '仿佛逆流而上的鱼'],
        '美好': ['如诗如画', '像一首未完的歌'],
    }
    
    # 随机替换（克制地）
    replacements_made = 0
    for literal, metaphors in imagery.items():
        if literal in text and replacements_made < 2 and random.random() < 0.3:
            text = text.replace(literal, random.choice(metaphors), 1)
            replacements_made += 1
    
    # 添加感官描写
    sensory_inserts = [
        '空气中弥漫着', '光线透过', '远处传来',
        '指尖触碰到', '目光所及之处',
    ]
    
    sentences = re.split(r'([。！？])', text)
    result = []
    sensory_added = False
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        # 偶尔添加感官描写开头
        if not sensory_added and random.random() < 0.15 and i > 0:
            sensory = random.choice(sensory_inserts)
            sent = sensory + '——' + sent
            sensory_added = True
        
        result.append(sent + punct)
    
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        result.append(sentences[-1])
    
    return ''.join(result)

def transform_weibo(text):
    """微博风格"""
    text = remove_formal_structure(text)
    text = replace_formal_words(text)
    
    # 微博要短，有态度
    sentences = re.split(r'([。！？])', text)
    result = []
    
    # 只保留前几句精华
    sent_count = 0
    max_sents = 5
    
    for i in range(0, len(sentences) - 1, 2):
        sent = sentences[i].strip()
        punct = sentences[i + 1] if i + 1 < len(sentences) else ''
        
        if not sent:
            continue
        
        sent_count += 1
        if sent_count > max_sents:
            break
        
        # 加态度
        if sent_count == 1 and random.random() < 0.4:
            attitude = random.choice(['说真的，', '讲道理，', ''])
            sent = attitude + sent
        
        result.append(sent + punct)
    
    text = ''.join(result)
    
    # 加话题
    text = add_emojis(text, 'casual', density=0.15)
    
    return text

# ─── 风格路由 ───

TRANSFORM_MAP = {
    'casual': transform_casual,
    'zhihu': transform_zhihu,
    'xiaohongshu': transform_xiaohongshu,
    'wechat': transform_wechat,
    'academic': transform_academic,
    'literary': transform_literary,
    'weibo': transform_weibo,
}

def apply_style(text, style_name):
    """应用指定风格"""
    if style_name not in STYLES:
        print(f'错误: 不支持的风格 "{style_name}"', file=sys.stderr)
        print(f'支持的风格: {", ".join(STYLES.keys())}', file=sys.stderr)
        sys.exit(1)
    
    transform_fn = TRANSFORM_MAP.get(style_name)
    if transform_fn:
        return transform_fn(text)
    return text

def list_styles():
    """列出所有可用风格"""
    print('可用的文本风格：\n')
    for style_id, config in STYLES.items():
        print(f'  {style_id:15s} {config["name"]:10s}  {config["description"]}')
    print(f'\n使用: python style_cn.py input.txt --style <风格> [-o output.txt]')

# ─── Main ───

def main():
    parser = argparse.ArgumentParser(description='中文文本风格转换 v2.0')
    parser.add_argument('file', nargs='?', help='输入文件路径')
    parser.add_argument('--style', help='目标风格')
    parser.add_argument('-o', '--output', help='输出文件路径')
    parser.add_argument('--list', action='store_true', help='列出所有风格')
    parser.add_argument('--seed', type=int, help='随机种子')
    
    args = parser.parse_args()
    
    if args.list:
        list_styles()
        sys.exit(0)
    
    if not args.style:
        print('错误: 必须指定 --style 参数', file=sys.stderr)
        list_styles()
        sys.exit(1)
    
    if args.seed is not None:
        random.seed(args.seed)
    
    # Read input
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
    
    result = apply_style(text, args.style)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'✓ 已保存到 {args.output} (风格: {STYLES[args.style]["name"]})')
    else:
        print(result)

if __name__ == '__main__':
    main()
