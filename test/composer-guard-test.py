#!/usr/bin/env python3
"""composer_guard.py 测试：与 bash 版本共用 test/fixtures/composer-frames.tsv。

运行: python test/composer-guard-test.py   （Windows 与类 Unix 均可）
"""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))
import composer_guard as cg  # noqa: E402

FIXTURES = os.path.join(ROOT, "test", "fixtures", "composer-frames.tsv")


def decode_printf_b(escaped):
    """解码 printf %b 风格的转义（\\NNN 八进制、\\0NNN、\\n、\\t、\\\\）。"""
    out = bytearray()
    i = 0
    raw = escaped.encode("utf-8")
    pattern = re.compile(rb"\\(0[0-7]{1,3}|[0-7]{1,3}|n|t|r|\\)")
    while i < len(raw):
        m = pattern.match(raw, i)
        if m:
            tok = m.group(1)
            if tok == b"n":
                out += b"\n"
            elif tok == b"t":
                out += b"\t"
            elif tok == b"r":
                out += b"\r"
            elif tok == b"\\":
                out += b"\\"
            else:
                digits = tok[1:] if tok.startswith(b"0") and len(tok) > 1 else tok
                out.append(int(digits, 8) & 0xFF)
            i = m.end()
        else:
            out.append(raw[i])
            i += 1
    return out.decode("utf-8", "replace")


def load_fixtures():
    cases = []
    with open(FIXTURES, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            name, expected, escaped = line.split("|", 2)
            # 与 bash 的 $(printf %b ...) 一致：去掉末尾换行
            cases.append((name, expected, decode_printf_b(escaped).rstrip("\n")))
    return cases


class FixtureTest(unittest.TestCase):
    def test_fixtures(self):
        cases = load_fixtures()
        self.assertGreater(len(cases), 20)
        for name, expected, frame in cases:
            with self.subTest(name=name):
                actual = "empty" if cg.frame_is_empty(frame) else "nonempty"
                self.assertEqual(actual, expected)


class SeamTest(unittest.TestCase):
    def test_sgr_parser(self):
        self.assertTrue(cg.sgr_is_supported("48;2;12;34;56"))
        self.assertFalse(cg.sgr_is_supported("48;2;12;34"))
        self.assertFalse(cg.sgr_is_supported("48;18446744073709551618;1;2;3"))

    def test_prompt_matcher(self):
        self.assertEqual(cg.prompt_suffix(" \x1b[1m›\x1b[22m draft »"),
                         "\x1b[22m draft »")
        self.assertIsNone(cg.prompt_suffix("output mentions ›"))

    def test_placeholder(self):
        self.assertTrue(cg.placeholder_is_empty("\x1b[0m\x1b[48;5;12m \x1b[2mAsk Codex"))
        self.assertFalse(cg.placeholder_is_empty("\x1b[48;2;2;34;56m Ask Codex"))

    def test_registry_extension(self):
        strategies = cg.STRATEGIES + [
            ("future", "^", lambda s: s == " Ready",
             lambda after: after == ["future footer"]),
        ]
        self.assertTrue(cg.frame_is_empty("^ Ready\nfuture footer", strategies))

    def test_windows_line_endings(self):
        frame = ("status\r\n›\x1b[0m \x1b[2mAsk Codex to do anything\x1b[0m\r\n\r\n"
                 "  gpt-5.6-sol medium · /workspace/project")
        self.assertTrue(cg.frame_is_empty(frame))


if __name__ == "__main__":
    unittest.main(verbosity=2)
