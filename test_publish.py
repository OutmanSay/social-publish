#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import unittest

import publish


ROOT = os.path.dirname(os.path.abspath(__file__))


class PublishTests(unittest.TestCase):
    def test_short_x_post_stays_single(self):
        self.assertEqual(publish.split_for_x("短消息"), ["短消息"])

    def test_long_x_post_is_split_under_weight_limit(self):
        source = "这是一个句子。" * 80
        parts = publish.split_for_x(source)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(publish.weighted_length(part) <= 260 for part in parts))
        self.assertEqual("".join(parts).replace("\n", ""), source.replace("\n", ""))

    def test_default_is_dry_run(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "publish.py"), "--platform", "weibo", "--text", "测试预演"],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(json.loads(proc.stdout)["dry_run"])

    def test_semantic_failure_is_not_success(self):
        self.assertFalse(publish.command_succeeded(0, '[{"status":"failed"}]'))
        self.assertFalse(publish.command_succeeded(0, '{"ok":false}'))
        self.assertTrue(publish.command_succeeded(0, '[{"status":"success"}]'))


if __name__ == "__main__":
    unittest.main()
