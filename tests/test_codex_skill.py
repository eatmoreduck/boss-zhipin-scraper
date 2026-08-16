import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / ".agents" / "skills" / "boss-zhipin-scraper" / "SKILL.md"
OPENAI_METADATA_PATH = (
    ROOT / ".agents" / "skills" / "boss-zhipin-scraper" / "agents" / "openai.yaml"
)


class CodexSkillTests(unittest.TestCase):
    def test_skill_manifest_has_standard_front_matter(self):
        text = SKILL_PATH.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        front_matter, _, instructions = text[4:].partition("\n---\n")
        self.assertTrue(instructions.strip())

        name = re.search(r"^name:\s*([^\n]+)$", front_matter, re.MULTILINE)
        description = re.search(r"^description:\s*(.+)$", front_matter, re.MULTILINE)
        self.assertIsNotNone(name)
        self.assertEqual(name.group(1).strip(), "boss-zhipin-scraper")
        self.assertIsNotNone(description)
        self.assertGreater(len(description.group(1).strip()), 20)

    def test_skill_describes_existing_cli_and_user_controlled_boundaries(self):
        text = SKILL_PATH.read_text(encoding="utf-8")

        for expected in (
            "scripts/boss_cdp_raw.py",
            "scripts/job_summary.py",
            "--check",
            "--setup-chrome",
            "code 37",
            "SMS",
            "Do not send messages",
        ):
            self.assertIn(expected, text)

    def test_codex_metadata_is_present_and_does_not_reference_local_data(self):
        text = OPENAI_METADATA_PATH.read_text(encoding="utf-8")

        self.assertIn("display_name:", text)
        self.assertIn("default_prompt:", text)
        self.assertNotIn("job-data", text)
        self.assertNotIn("Cookies", text)


if __name__ == "__main__":
    unittest.main()
