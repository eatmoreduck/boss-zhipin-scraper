import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


# 同 tests/test_chrome_setup.py：Windows GBK 控制台无法编码 emoji，统一重配 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


ROOT_PATH = pathlib.Path(__file__).resolve().parents[1]
SUMMARY_SCRIPT_PATH = ROOT_PATH / "scripts" / "job_summary.py"


def load_summary_module():
    sys.modules.setdefault("websocket", mock.Mock())
    sys.modules.setdefault("requests", mock.Mock())
    spec = importlib.util.spec_from_file_location("job_summary", SUMMARY_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class JobSummaryTests(unittest.TestCase):
    def test_module_exists_without_resume_file_scoring(self):
        self.assertTrue(SUMMARY_SCRIPT_PATH.exists())
        text = SUMMARY_SCRIPT_PATH.read_text(encoding="utf-8")
        for forbidden in ("pdfplumber", "parse_resume", "score_resume", "--resume"):
            self.assertNotIn(forbidden, text)

    def test_load_jobs_file_supports_scraper_output_shape(self):
        module = load_summary_module()
        payload = {
            "keyword": "AI Agent",
            "city": "上海",
            "jobs": [
                {
                    "title": "AI Agent工程师",
                    "salary": "30-60K",
                    "location": "上海·浦东新区",
                    "tags": "3-5年 | 本科 | Python",
                    "boss_name": "甲公司",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "boss_jobs_20260625_1200.json"
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            jobs, metadata = module.load_jobs_file(str(path))

        self.assertEqual(len(jobs), 1)
        self.assertEqual(metadata["keyword"], "AI Agent")
        self.assertEqual(metadata["city"], "上海")

    def test_build_summary_counts_market_dimensions(self):
        module = load_summary_module()
        jobs = [
            {
                "job_id": "job-a",
                "title": "AI Agent工程师",
                "salary": "30-60K",
                "location": "上海·浦东新区",
                "tags": "3-5年 | 本科 | Python | LLM",
                "job_labels": ["AIGC"],
                "boss_name": "甲公司",
            },
            {
                "job_id": "job-b",
                "title": "LLM应用工程师",
                "salary": "30-60K",
                "location": "上海·浦东新区",
                "tags": "3-5年 | 本科 | RAG",
                "skills": "LangChain | RAG",
                "boss_name": "甲公司",
            },
            {
                "job_id": "job-c",
                "title": "AI平台工程师",
                "salary": "40-70K",
                "location": "上海·徐汇区",
                "tags": "5-10年 | 硕士 | Python",
                "boss_name": "乙公司",
            },
        ]
        details = [
            {"job_id": "job-a", "skill_tags": ["Python", "LLM"], "jd": "负责 Python LLM Agent RAG 应用开发"},
            {"job_id": "job-b", "skill_tags": ["RAG"], "jd": "建设 LLM RAG 检索增强生成系统"},
        ]

        summary = module.build_summary(jobs, details, search_keyword="AI Agent", top=5)

        self.assertEqual(summary["total_jobs"], 3)
        self.assertEqual(summary["total_details"], 2)
        self.assertEqual(summary["salary_ranges"][0], ("30-60K", 2))
        self.assertIn(("3-5年", 2), summary["experience"])
        self.assertIn(("本科", 2), summary["degrees"])
        self.assertIn(("浦东新区", 2), summary["districts"])
        self.assertIn(("甲公司", 2), summary["companies"])
        self.assertIn(("Python", 3), summary["skill_tags"])
        self.assertIn(("RAG", 3), summary["skill_tags"])
        self.assertIn(("LangChain", 1), summary["skill_tags"])
        self.assertIn(("AIGC", 1), summary["skill_tags"])
        self.assertTrue(any(term == "LLM" for term, _ in summary["jd_terms"]))

    def test_build_summary_uses_list_skills_without_details(self):
        module = load_summary_module()
        jobs = [
            {
                "title": "AI Agent工程师",
                "salary": "30-60K",
                "location": "上海·浦东新区",
                "tags": "3-5年 | 本科",
                "skills": "Python | LLM | RAG",
                "boss_name": "甲公司",
            }
        ]

        summary = module.build_summary(jobs, details=[], search_keyword="AI Agent")

        self.assertIn(("Python", 1), summary["skill_tags"])
        self.assertIn(("LLM", 1), summary["skill_tags"])
        self.assertIn(("RAG", 1), summary["skill_tags"])
        self.assertEqual(summary["jd_terms"], [])

    def test_build_summary_filters_details_to_current_jobs(self):
        module = load_summary_module()
        jobs = [
            {
                "job_id": "current",
                "title": "AI Agent工程师",
                "salary": "30-60K",
                "location": "上海·浦东新区",
                "tags": "3-5年 | 本科",
                "skills": "Python",
                "boss_name": "甲公司",
            }
        ]
        details = [
            {"job_id": "current", "skill_tags": ["Python"], "jd": "Python LLM Agent"},
            {"job_id": "other", "skill_tags": ["Rust"], "jd": "Rust Go"},
        ]

        summary = module.build_summary(jobs, details, search_keyword="AI Agent")

        self.assertEqual(summary["total_details"], 1)
        self.assertIn(("Python", 2), summary["skill_tags"])
        self.assertNotIn(("Rust", 1), summary["skill_tags"])

    def test_jd_terms_use_word_boundaries_for_english_terms(self):
        module = load_summary_module()
        details = [
            {"skill_tags": [], "jd": "负责 Django 和 AIGC 平台建设"},
        ]

        summary = module.build_summary([], details, search_keyword="Go AI")
        terms = {term for term, _ in summary["jd_terms"]}

        self.assertNotIn("Go", terms)
        self.assertNotIn("AI", terms)

    def test_jd_noise_terms_are_filtered(self):
        """JD 正文夹带的页面噪音（安全声明/工商信息/推荐栏/地名）应被过滤，只留真实技能词。

        回归:真实数据里 JD 高频词一度全是噪音（职位描述/直聘严禁用人/上海/工商信息等），
        污染了摘要和提示词。job_summary 层维护黑名单剔除它们。
        """
        module = load_summary_module()
        details = [
            {
                "skill_tags": [],
                "jd": (
                    "职位描述\n熟练使用 Python 和 LLM，熟悉 RAG\n"
                    "BOSS 安全提示：直聘严禁用人单位和招聘者用户做出任何损害求职者合法权益\n"
                    "工商信息 公司名称 法定代表人 注册资金\n"
                    "精选职位 城市招聘 推荐公司\n"
                    "工作地点：上海"
                ),
            },
        ]

        summary = module.build_summary([], details, search_keyword="Python")
        terms = {term for term, _ in summary["jd_terms"]}

        # 真实技能应保留
        self.assertIn("Python", terms)
        self.assertIn("LLM", terms)
        self.assertIn("RAG", terms)
        # 页面噪音应被全部过滤
        for noise in ("职位描述", "安全提示", "直聘严禁用人", "工商信息",
                      "公司名称", "法定代表人", "注册资金", "精选职位",
                      "城市招聘", "推荐公司", "上海"):
            self.assertNotIn(noise, terms, f"噪音词 {noise} 不应出现在 JD 高频词中")

    def test_explicit_details_path_does_not_fallback_to_latest(self):
        module = load_summary_module()
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = pathlib.Path(tmp)
            list_path = result_dir / "boss_jobs_20260625_1200.json"
            latest_detail = result_dir / "boss_details_20260625_1300.json"
            missing_detail = result_dir / "missing_details.json"
            list_path.write_text('{"jobs":[]}', encoding="utf-8")
            latest_detail.write_text('[{"job_id":"wrong"}]', encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                module.load_details_for_input(
                    str(list_path),
                    detail_path=str(missing_detail),
                    result_dir=str(result_dir),
                )

    def test_output_mode_flags_are_mutually_exclusive(self):
        module = load_summary_module()

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                module.build_arg_parser().parse_args(["--summary-only", "--prompt-only"])

    def test_top_must_be_positive(self):
        module = load_summary_module()

        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                module.build_arg_parser().parse_args(["--top", "0"])

    def test_main_reports_bad_input_without_traceback(self):
        module = load_summary_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "boss_jobs_bad.json"
            path.write_text("{bad json", encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()) as stdout:
                code = module.main(["--input", str(path)])

        self.assertEqual(code, 1)
        self.assertIn("无法加载输入文件", stdout.getvalue())

    def test_build_prompt_uses_aggregate_context_without_scores(self):
        module = load_summary_module()
        summary = {
            "keyword": "AI Agent",
            "city": "上海",
            "total_jobs": 3,
            "total_details": 2,
            "salary_ranges": [("30-60K", 2)],
            "experience": [("3-5年", 2)],
            "degrees": [("本科", 2)],
            "districts": [("浦东新区", 2)],
            "companies": [("甲公司", 2)],
            "skill_tags": [("Python", 3), ("RAG", 2)],
            "jd_terms": [("LLM", 2), ("Agent", 1)],
        }

        prompt = module.build_prompt(summary)

        self.assertIn("岗位市场摘要", prompt)
        self.assertIn("Python", prompt)
        self.assertIn("RAG", prompt)
        self.assertIn("不要虚构经历", prompt)
        self.assertNotIn("匹配分", prompt)
        self.assertNotIn("分数", prompt)

    def test_summary_script_is_documented_and_packaged(self):
        readme = (ROOT_PATH / "README.md").read_text(encoding="utf-8")
        changelog = (ROOT_PATH / "CHANGELOG.md").read_text(encoding="utf-8")
        skill = (ROOT_PATH / "SKILL.md").read_text(encoding="utf-8")
        pyproject = (ROOT_PATH / "pyproject.toml").read_text(encoding="utf-8")

        for document in (readme, changelog, skill):
            self.assertIn("job_summary.py", document)
            self.assertIn("提示词", document)
        self.assertIn("cp boss-zhipin-scraper/scripts/job_summary.py", skill)
        self.assertIn('boss-summary = "scripts.job_summary:main"', pyproject)


if __name__ == "__main__":
    unittest.main()
