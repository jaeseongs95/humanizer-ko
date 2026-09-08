#!/usr/bin/env python3
"""정상 패키지와 손상된 배포 파일·행동 기록에 대한 검증기의 동작을 확인한다."""

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
        for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "skills",
                     "examples", ".codex-plugin", ".claude-plugin", "scripts", "tests"):
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

    def run_behavior_validator(self):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(self.root / "scripts/check-behavior-artifacts.py")],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
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

    def test_missing_installed_license(self):
        (self.root / "skills" / "humanizer-ko" / "LICENSE").unlink()
        self.assert_rejected("skills\\humanizer-ko\\LICENSE" if sys.platform == "win32" else
                             "skills/humanizer-ko/LICENSE")

    def test_installed_notice_mismatch(self):
        self.replace("skills/humanizer-ko/THIRD_PARTY_NOTICES.md", "비공식", "공식")
        self.assert_rejected("독립형 Skill의 THIRD_PARTY_NOTICES.md")

    def test_behavior_url_suffix_rejected(self):
        evidence_path = self.root / "tests" / "evidence" / "2.0.0" / "final.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["outputs"]["R02"] = evidence["outputs"]["R02"].replace(
            "https://example.com/runbook", "https://example.com/runbook-malformed",
        )
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        result = self.run_behavior_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("URL 불일치", result.stderr)

    def test_claude_plugin_version_mismatch(self):
        path = self.root / ".claude-plugin/plugin.json"
        plugin = json.loads(path.read_text(encoding="utf-8"))
        major, minor, patch = map(int, plugin["version"].split("."))
        plugin["version"] = f"{major + 1}.{minor}.{patch}"
        path.write_text(json.dumps(plugin, ensure_ascii=False), encoding="utf-8")
        self.assert_rejected("버전을 일치")

    def test_codex_plugin_version_mismatch(self):
        path = self.root / ".codex-plugin/plugin.json"
        plugin = json.loads(path.read_text(encoding="utf-8"))
        major, minor, patch = map(int, plugin["version"].split("."))
        plugin["version"] = f"{major + 1}.{minor}.{patch}"
        path.write_text(json.dumps(plugin, ensure_ascii=False), encoding="utf-8")
        self.assert_rejected("버전을 일치")

    def test_pattern_gap(self):
        self.replace("skills/humanizer-ko/SKILL.md", "### 25.", "### 26.")
        self.assert_rejected("패턴 번호")

    def test_missing_description_boundary(self):
        self.replace("skills/humanizer-ko/SKILL.md", "일반 질문", "일상 응답")
        self.assert_rejected("description에 호출 경계")

    def test_wrong_prompt(self):
        self.replace("skills/humanizer-ko/agents/openai.yaml", "$humanizer-ko", "$humanizer")
        self.assert_rejected("기본 프롬프트")

    def test_implicit_invocation_disabled(self):
        self.replace("skills/humanizer-ko/agents/openai.yaml", "allow_implicit_invocation: true",
                      "allow_implicit_invocation: false")
        self.assert_rejected("자동 Skill 선택")

    def test_wrong_policy_section(self):
        self.replace("skills/humanizer-ko/agents/openai.yaml", "policy:", "policcy:")
        self.assert_rejected("최상위 policy:")

    def test_missing_codex_instructions(self):
        (self.root / "examples" / "AGENTS.humanizer-ko.md").unlink()
        self.assert_rejected("AGENTS.humanizer-ko.md")

    def test_missing_chatgpt_instructions(self):
        (self.root / "examples" / "CHATGPT.custom-instructions.humanizer-ko.md").unlink()
        self.assert_rejected("CHATGPT.custom-instructions.humanizer-ko.md")

    def test_missing_claude_instructions(self):
        (self.root / "examples" / "CLAUDE.humanizer-ko.md").unlink()
        self.assert_rejected("CLAUDE.humanizer-ko.md")

    def test_duplicate_skill(self):
        duplicate = self.root / "nested"
        duplicate.mkdir()
        shutil.copy2(self.root / "skills/humanizer-ko/SKILL.md", duplicate / "SKILL.md")
        self.assert_rejected("skills/humanizer-ko")

    def test_wrong_codex_skill_path(self):
        self.replace(".codex-plugin/plugin.json", '"skills": "./skills/"',
                     '"skills": "./"')
        self.assert_rejected("Codex 플러그인의 skills")

    def test_wrong_claude_skill_path(self):
        self.replace(".claude-plugin/plugin.json", '"skills": ["./skills/humanizer-ko"]',
                     '"skills": ["./"]')
        self.assert_rejected("Claude 플러그인의 skills")

    def test_missing_host_invocation(self):
        self.replace("examples/CHATGPT.custom-instructions.humanizer-ko.md",
                     "`@humanizer-ko`", "`humanizer-ko`")
        self.assert_rejected("@humanizer-ko")

    def test_unsupported_codex_component(self):
        self.replace(".codex-plugin/plugin.json", '"skills": "./skills/",',
                     '"skills": "./skills/",\n  "hooks": {},')
        self.assert_rejected("구성 요소를 제거")

    def test_wrong_json_shape(self):
        (self.root / ".codex-plugin/plugin.json").write_text("[]", encoding="utf-8")
        self.assert_rejected("최상위 값은 객체")


if __name__ == "__main__":
    unittest.main()
