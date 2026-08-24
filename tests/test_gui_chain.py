"""boss_gui 薄壳的纯逻辑测试：命令行拼装 + 自动接跑摘要的判定。

不创建窗口、不依赖 Chrome / 网络；只验证 GUI 不会把参数拼错。
"""

import importlib
import os
import sys
import unittest
from unittest import mock

import scripts.boss_cdp_raw as boss_mod
from scripts import boss_gui


class BuildScrapeArgsTest(unittest.TestCase):
    def test_defaults_json_no_detail_no_analysis(self):
        args = boss_gui.build_scrape_args("AI Agent", "上海", 3)
        self.assertEqual(args[0], sys.executable)
        self.assertIn("--keyword", args)
        self.assertEqual(args[args.index("--keyword") + 1], "AI Agent")
        self.assertEqual(args[args.index("--city") + 1], "上海")
        self.assertEqual(args[args.index("--pages") + 1], "3")
        self.assertIn("--no-detail", args)
        self.assertNotIn("--detail", args)
        self.assertNotIn("--analysis", args)
        self.assertNotIn("--format", args)  # json 是默认，不显式传

    def test_csv_detail_analysis_and_custom_port(self):
        args = boss_gui.build_scrape_args(
            "Java", "北京", 5, cdp_port=9223, fmt="csv", detail=True, analysis=True,
        )
        self.assertEqual(args[args.index("--format") + 1], "csv")
        self.assertEqual(args[args.index("--cdp-port") + 1], "9223")
        self.assertIn("--detail", args)
        self.assertNotIn("--no-detail", args)
        self.assertIn("--analysis", args)

    def test_output_and_merge(self):
        args = boss_gui.build_scrape_args("Python", "深圳", 2, output=r"D:\r\a.json", merge=r"D:\r\old.json")
        self.assertEqual(args[args.index("--output") + 1], r"D:\r\a.json")
        self.assertEqual(args[args.index("--merge") + 1], r"D:\r\old.json")

    def test_detail_output_flag(self):
        args = boss_gui.build_scrape_args(
            "Python", "上海", 1, detail=True,
            output=r"D:\r\a.json", detail_output=r"D:\r\d.json",
        )
        self.assertEqual(args[args.index("--detail-output") + 1], r"D:\r\d.json")


class BuildOtherArgsTest(unittest.TestCase):
    def test_summary_args(self):
        args = boss_gui.build_summary_args(top=15)
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(args[args.index("--top") + 1], "15")

    def test_summary_args_with_input(self):
        args = boss_gui.build_summary_args(top=8, input_path=r"D:\r\multi.json")
        self.assertEqual(args[args.index("--input") + 1], r"D:\r\multi.json")

    def test_summary_args_with_result_dir(self):
        args = boss_gui.build_summary_args(top=8, result_dir=r"D:\r")
        self.assertEqual(args[args.index("--result-dir") + 1], r"D:\r")

    def test_check_args(self):
        args = boss_gui.build_check_args(9222)
        self.assertIn("--check", args)
        self.assertEqual(args[args.index("--cdp-port") + 1], "9222")

    def test_setup_chrome_does_not_wait_for_login(self):
        args = boss_gui.build_setup_chrome_args(9222)
        self.assertIn("--setup-chrome", args)
        self.assertIn("--no-wait-login", args)  # GUI 启动后立即返回，登录由用户完成

    def test_smoke_and_stop_chrome(self):
        self.assertIn("--smoke-test", boss_gui.build_smoke_args(9222))
        self.assertIn("--stop-chrome", boss_gui.build_stop_chrome_args(9222))


class AutoSummaryDecisionTest(unittest.TestCase):
    def test_only_zero_exit_code_triggers_summary(self):
        self.assertTrue(boss_gui.should_auto_summary(0))
        self.assertFalse(boss_gui.should_auto_summary(1))
        self.assertFalse(boss_gui.should_auto_summary(2))


class SplitKeywordsTest(unittest.TestCase):
    def test_splits_by_common_separators(self):
        self.assertEqual(
            boss_gui.split_keywords("AI Agent,Python，Java;产品经理；前端\n后端"),
            ["AI Agent", "Python", "Java", "产品经理", "前端", "后端"],
        )

    def test_strips_and_ignores_empty(self):
        self.assertEqual(boss_gui.split_keywords("  AI  ,  ,  Python  "), ["AI", "Python"])
        self.assertEqual(boss_gui.split_keywords(""), [])
        self.assertEqual(boss_gui.split_keywords("   "), [])


class BuildMultiKeywordStepsTest(unittest.TestCase):
    def test_single_keyword_explicit_output_no_merge(self):
        steps, final_path, parts = boss_gui.build_multi_keyword_steps(
            ["AI Agent"], "上海", 2, result_dir=r"D:\r", timestamp="20260823_1200",
        )
        self.assertEqual(len(steps), 1)
        self.assertEqual(final_path, r"D:\r\boss_jobs_20260823_1200.json")
        self.assertEqual(parts, [])
        first_args, _ = steps[0]
        self.assertNotIn("--merge", first_args)
        self.assertEqual(first_args[first_args.index("--output") + 1], final_path)

    def test_multi_keyword_chains_merge_and_returns_parts(self):
        steps, final_path, parts = boss_gui.build_multi_keyword_steps(
            ["AI", "Python", "Java"], "上海", 2,
            result_dir=r"D:\r", timestamp="20260823_1200",
        )
        self.assertEqual(len(steps), 3)
        self.assertEqual(final_path, r"D:\r\boss_jobs_20260823_1200_multi.json")
        self.assertEqual(parts, [
            r"D:\r\boss_jobs_20260823_1200_multi.part1.json",
            r"D:\r\boss_jobs_20260823_1200_multi.part2.json",
        ])
        first_args, _ = steps[0]
        self.assertNotIn("--merge", first_args)
        self.assertEqual(first_args[first_args.index("--output") + 1], final_path)
        second_args, _ = steps[1]
        self.assertEqual(second_args[second_args.index("--merge") + 1], final_path)
        self.assertEqual(second_args[second_args.index("--output") + 1], parts[0])
        third_args, _ = steps[2]
        self.assertEqual(third_args[third_args.index("--merge") + 1], parts[0])
        self.assertEqual(third_args[third_args.index("--output") + 1], parts[1])

    def test_multi_keyword_detail_outputs_are_distinct(self):
        steps, _, _ = boss_gui.build_multi_keyword_steps(
            ["AI", "Python"], "上海", 2, detail=True,
            result_dir=r"D:\r", timestamp="20260823_1200",
        )
        first, second = steps[0][0], steps[1][0]
        self.assertEqual(
            first[first.index("--detail-output") + 1],
            r"D:\r\boss_details_20260823_1200_multi.json",
        )
        self.assertEqual(
            second[second.index("--detail-output") + 1],
            r"D:\r\boss_details_20260823_1200_multi.part1.json",
        )


class DefaultResultDirEnvTest(unittest.TestCase):
    def test_env_override_honored(self):
        with mock.patch.dict(os.environ, {"BOSS_RESULT_DIR": r"D:\boss\job-result"}):
            importlib.reload(boss_mod)
            self.assertTrue(
                boss_mod.DEFAULT_RESULT_DIR.replace("\\", "/").startswith("D:/boss/job-result")
            )
        importlib.reload(boss_mod)  # 环境变量已还原，重新计算默认值，避免影响后续用例


if __name__ == "__main__":
    unittest.main()
