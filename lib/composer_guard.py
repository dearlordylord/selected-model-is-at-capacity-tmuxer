"""composer_guard — lib/composer-guard.bash 的纯 Python 移植（无需 bash）。

判断 Codex 输入框是否为"空白的暗色占位符"，从而可以安全地输入文本。
任何无法理解的终端格式都按"失败即关闭"处理（返回 False）。
行为与 bash 版本一致，使用同一套 test/fixtures/composer-frames.tsv 验证。
"""

ESC = "\x1b"
FAINT_SGR = "2"

CODEX_PLACEHOLDERS = frozenset([
    "Ask Codex to do anything",
    "Explain this codebase",
    "Summarize recent commits",
    "Implement {feature}",
    "Find and fix a bug in @filename",
    "Write tests for @filename",
    "Improve documentation in @filename",
    "Run /review on my current changes",
    "Use /skills to list available skills",
])

FOOTER_MARKERS = (" default · /", " low · /", " medium · /", " high · /",
                  " xhigh · /", " max · /", " ultra · /")


def _is_space(ch):
    return ch.isspace()


def sgr_is_supported(params):
    """SGR 参数列表是否为已知格式（保守处理，未知即拒绝）。"""
    if params == "":
        return True                     # ESC[m 等于重置
    if params.startswith(";") or params.endswith(";") or ";;" in params:
        return False
    parts = params.split(";")

    def num(s):
        if not s.isdigit() or not s.isascii() or len(s) > 3:
            return None
        return int(s)

    i = 0
    while i < len(parts):
        value = num(parts[i])
        if value is None:
            return False
        if value in (0, 1, 2, 3, 4, 7, 9, 22, 23, 24, 27, 29, 39, 49):
            i += 1
        elif value in (38, 48):
            if i + 1 >= len(parts):
                return False
            mode = num(parts[i + 1])
            if mode == 5:
                if i + 2 >= len(parts):
                    return False
                v = num(parts[i + 2])
                if v is None or v > 255:
                    return False
                i += 3
            elif mode == 2:
                if i + 4 >= len(parts):
                    return False
                for p in parts[i + 2:i + 5]:
                    v = num(p)
                    if v is None or v > 255:
                        return False
                i += 5
            else:
                return False
        elif 30 <= value <= 37 or 40 <= value <= 47 or 90 <= value <= 97 \
                or 100 <= value <= 107:
            i += 1
        else:
            return False
    return True


def parse_leading_sgr(text):
    """解析开头的一个 ESC[...m，返回 (params, remainder)；失败返回 None。"""
    if not text.startswith(ESC + "["):
        return None
    body = text[2:]
    end = body.find("m")
    if end < 0:
        return None
    params = body[:end]
    if not sgr_is_supported(params):
        return None
    return params, body[end + 1:]


def strip_leading_formatting(text):
    """去掉行首空白与 SGR；遇到不支持的 SGR 返回 None。"""
    while text:
        trimmed = text.lstrip()
        if trimmed != text:
            text = trimmed
            continue
        if text.startswith(ESC + "["):
            parsed = parse_leading_sgr(text)
            if parsed is None:
                return None
            text = parsed[1]
        else:
            break
    return text


def strip_all_formatting(text):
    """去掉所有受支持的 SGR；遇到其他转义序列返回 None。"""
    plain = []
    while text:
        if text.startswith(ESC + "["):
            parsed = parse_leading_sgr(text)
            if parsed is None:
                return None
            text = parsed[1]
        elif text.startswith(ESC):
            return None
        else:
            plain.append(text[0])
            text = text[1:]
    return "".join(plain)


def placeholder_text_is_valid(text):
    """占位符文本中可见字符必须一直保持暗色（faint）。"""
    faint = True
    visible = False
    while text:
        if text.startswith(ESC + "["):
            parsed = parse_leading_sgr(text)
            if parsed is None:
                return False
            params, text = parsed
            if params == "":
                faint = False
            else:
                for part in params.split(";"):
                    v = int(part)
                    if v in (0, 22):
                        faint = False
                    elif v == 2:
                        faint = True
        elif text.startswith(ESC):
            return False
        else:
            if not _is_space(text[0]):
                if not faint:
                    return False
                visible = True
            text = text[1:]
    return visible


def placeholder_is_empty(text):
    """空白/受支持 SGR 之后必须紧跟精确的 faint SGR 与有效占位符。"""
    while text:
        trimmed = text.lstrip()
        if trimmed != text:
            text = trimmed
            continue
        if not text.startswith(ESC + "["):
            return False
        parsed = parse_leading_sgr(text)
        if parsed is None:
            return False
        params, rest = parsed
        if params == FAINT_SGR:
            return placeholder_text_is_valid(rest)
        text = rest
    return False


def codex_placeholder_is_empty(suffix):
    if not placeholder_is_empty(suffix):
        return False
    while suffix:
        if suffix.startswith(ESC + "["):
            parsed = parse_leading_sgr(suffix)
            if parsed is None:
                return False
            suffix = parsed[1]
        elif _is_space(suffix[0]):
            suffix = suffix[1:]
        else:
            break
    text = strip_all_formatting(suffix)
    return text is not None and text in CODEX_PLACEHOLDERS


def codex_context_matches(after_lines):
    """输入框下方应为：空行、状态栏页脚、其余空行。"""
    footer_seen = False
    for row, line in enumerate(after_lines or [""], start=1):
        plain = strip_all_formatting(line.rstrip("\r"))
        if plain is None:
            return False
        plain = plain.strip()
        if row == 2:
            if any(m in plain for m in FOOTER_MARKERS):
                footer_seen = True
            else:
                return False
        elif plain:
            return False
    return footer_seen


# 策略注册表：(名称, 提示符, 空判定, 上下文判定)
STRATEGIES = [
    ("codex_standard_max", "›", codex_placeholder_is_empty, codex_context_matches),
    ("codex_ultra", "»", codex_placeholder_is_empty, codex_context_matches),
]

NO_MATCH, MATCH, ABORT = 1, 0, 2


def prompt_match(line, strategies=None):
    """返回 (status, strategy_index, suffix)。提示符必须是首个可见字符。"""
    strategies = STRATEGIES if strategies is None else strategies
    visible = strip_leading_formatting(line)
    if visible is None:
        if any(glyph in line for _, glyph, _, _ in strategies):
            return ABORT, None, None
        return NO_MATCH, None, None
    for index, (_, glyph, _, _) in enumerate(strategies):
        if not glyph:
            return ABORT, None, None
        if visible.startswith(glyph):
            return MATCH, index, visible[len(glyph):]
    return NO_MATCH, None, None


def prompt_suffix(line):
    status, _, suffix = prompt_match(line)
    return suffix if status == MATCH else None


def frame_is_empty(frame, strategies=None):
    """对抓取到的整帧画面（含 ANSI）判断输入框是否为空。"""
    strategies = STRATEGIES if strategies is None else strategies
    lines = [l.rstrip("\r") for l in frame.split("\n")]
    candidate = None
    for index, line in enumerate(lines):
        status, sidx, suffix = prompt_match(line, strategies)
        if status == ABORT:
            return False
        if status == MATCH:
            candidate = (index, sidx, suffix)
    if candidate is None:
        return False
    index, sidx, suffix = candidate
    _, _, empty_matcher, context_matcher = strategies[sidx]
    if not context_matcher(lines[index + 1:]):
        return False
    return bool(empty_matcher(suffix))
