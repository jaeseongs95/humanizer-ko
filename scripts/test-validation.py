#!/usr/bin/env python3
"""정상 패키지와 손상된 배포 파일에 대한 검증기의 동작을 확인한다."""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="humanizer-ko-package-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("SKILL.md", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
                     "agents", "examples", ".claude-plugin", "scripts", "tests"):
            source, dest = ROOT / name, self.root / name
            if source.is_dir():
                shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, dest)

    def run_validator(self):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(self.root / "scripts/validate-package.py")],
            capture_output=True, text=True, encoding="utf-8",
        )

    def replace(self, filename, old, new):
        path = self.root / filename
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def assert_rejected(self, diagnostic):
        result = self.run_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_valid_package(self):
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_license_text_change(self):
        self.replace("LICENSE", "without restriction", "with restriction")
        self.assert_rejected("MIT 전문")

    def test_missing_notice(self):
        (self.root / "THIRD_PARTY_NOTICES.md").unlink()
        self.assert_rejected("THIRD_PARTY_NOTICES.md")

    def test_plugin_version_mismatch(self):
        path = self.root / ".claude-plugin/plugin.json"
        plugin = json.loads(path.read_text(encoding="utf-8"))
        major, minor, patch = map(int, plugin["version"].split("."))
        plugin["version"] = f"{major + 1}.{minor}.{patch}"
        path.write_text(json.dumps(plugin, ensure_ascii=False), encoding="utf-8")
        self.assert_rejected("버전을 일치")

    def test_pattern_gap(self):
        self.replace("SKILL.md", "### 25.", "### 26.")
        self.assert_rejected("패턴 번호")

    def test_wrong_prompt(self):
        self.replace("agents/openai.yaml", "$humanizer-ko", "$humanizer")
        self.assert_rejected("기본 프롬프트")

    def test_implicit_invocation_disabled(self):
        self.replace("agents/openai.yaml", "allow_implicit_invocation: true",
                     "allow_implicit_invocation: false")
        self.assert_rejected("자동 Skill 선택")

    def test_missing_global_instructions(self):
        (self.root / "examples" / "AGENTS.humanizer-ko.md").unlink()
        self.assert_rejected("AGENTS.humanizer-ko.md")

    def test_duplicate_skill(self):
        duplicate = self.root / "nested"
        duplicate.mkdir()
        shutil.copy2(self.root / "SKILL.md", duplicate / "SKILL.md")
        self.assert_rejected("SKILL.md 하나")

    def test_wrong_json_shape(self):
        (self.root / ".claude-plugin/plugin.json").write_text("[]", encoding="utf-8")
        self.assert_rejected("최상위 값은 객체")


if __name__ == "__main__":
    unittest.main()
