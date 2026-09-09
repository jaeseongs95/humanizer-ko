#!/usr/bin/env python3
"""정상 패키지와 손상된 배포 파일·행동 기록에 대한 검증기의 동작을 확인한다."""

from pathlib import Path
import hashlib
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

    def run_behavior_validator(self, evidence=None):
        command = [
            sys.executable, "-X", "utf8",
            str(self.root / "scripts/check-behavior-artifacts.py"),
        ]
        if evidence is not None:
            command.append(str(self.root / evidence))
        return subprocess.run(
            command,
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
        )

    def run_suite_payload_validator(self, *arguments):
        return subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(self.root / "scripts/validate-suite-payload.py"),
                *arguments,
            ],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8",
        )

    @staticmethod
    def content_hash(path):
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def read_json(self, relative):
        path = self.root / relative
        return path, json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def write_json(path, document):
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    def rebind_audit_to_evidence(self, case_id=None):
        evidence_path = self.root / "tests/evidence/2.0.1/final.json"
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        audit["bindings"]["evidenceSha256"] = self.content_hash(evidence_path)
        if case_id is not None:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            output = evidence["outputs"][case_id].replace("\r\n", "\n").replace("\r", "\n")
            audit["results"][case_id]["outputSha256"] = hashlib.sha256(
                output.encode("utf-8")
            ).hexdigest()
        self.write_json(audit_path, audit)

    def rebind_case_set(self):
        case_path = self.root / "tests/cases/2.0.1.json"
        case_hash = self.content_hash(case_path)
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        evidence["bindings"]["caseSet"]["sha256"] = case_hash
        self.write_json(evidence_path, evidence)
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        audit["bindings"]["caseSetSha256"] = case_hash
        audit["bindings"]["evidenceSha256"] = self.content_hash(evidence_path)
        self.write_json(audit_path, audit)

    def assert_behavior_rejected(self, diagnostic):
        result = self.run_behavior_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

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

    def assert_suite_payload_rejected(self, diagnostic):
        result = self.run_suite_payload_validator()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(diagnostic, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_valid_package(self):
        result = self.run_validator()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_suite_payload(self):
        result = self.run_suite_payload_validator("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "skills/humanizer-ko/SKILL.md -> skills/humanizer-ko/SKILL.md",
            result.stdout,
        )
        self.assertNotIn("README.md", result.stdout)
        self.assertNotIn(".codex-plugin", result.stdout)

    def test_suite_payload_rejects_repository_readme(self):
        path = self.root / "skills/humanizer-ko/README.md"
        path.write_text("# 저장소 전용 설명\n", encoding="utf-8")
        self.assert_suite_payload_rejected("저장소 전용 파일")

    def test_suite_payload_rejects_broken_local_link(self):
        path = self.root / "skills/humanizer-ko/SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n[없는 참고 자료](references/missing.md)\n",
            encoding="utf-8",
        )
        self.assert_suite_payload_rejected("로컬 링크 대상이 없습니다")

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

    def test_valid_behavior_artifacts(self):
        result = self.run_behavior_validator()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_schema2_checks_internal_protection_with_limitation(self):
        result = self.run_behavior_validator("tests/evidence/2.0.0/final.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("현재 Skill", result.stdout)
        self.assertIn("검증할 수 없습니다", result.stdout)

    def test_skill_canonical_tamper_rejected(self):
        self.replace("skills/humanizer-ko/SKILL.md", "## 작업 순서", "## 작업 절차")
        self.assert_behavior_rejected("bindings.skill")

    def test_case_set_canonical_tamper_rejected(self):
        path = self.root / "tests/cases/2.0.1.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_behavior_rejected("bindings.caseSet")

    def test_missing_case_request_rejected(self):
        case_path, case_set = self.read_json("tests/cases/2.0.1.json")
        case_set["cases"][0].pop("request")
        self.write_json(case_path, case_set)
        self.assert_behavior_rejected("R01.request")

    def test_request_protection_tokens_are_not_required_in_output(self):
        case_path, case_set = self.read_json("tests/cases/2.0.1.json")
        marker = "메타 지시의 “복사 금지”와 `request-only` 및 https://meta.invalid 값"
        case_set["cases"][0]["request"] += " " + marker
        self.assertNotIn(marker, case_set["cases"][0]["input"])
        self.write_json(case_path, case_set)
        _, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        self.assertNotIn(marker, evidence["outputs"]["R01"])
        self.rebind_case_set()
        result = self.run_behavior_validator()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_protocol_canonical_tamper_rejected(self):
        path = self.root / "tests/EVALUATION_PROTOCOL.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_behavior_rejected("bindings.protocol")

    def test_output_tamper_rejected(self):
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        evidence["outputs"]["R01"] += " 변조"
        self.write_json(evidence_path, evidence)
        self.assert_behavior_rejected("evidenceSha256")

    def test_audit_output_hash_tamper_rejected(self):
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        audit["results"]["R01"]["outputSha256"] = "0" * 64
        self.write_json(audit_path, audit)
        self.assert_behavior_rejected("outputSha256")

    def test_missing_case_output_rejected(self):
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        evidence["outputs"].pop("T07")
        self.write_json(evidence_path, evidence)
        self.rebind_audit_to_evidence()
        self.assert_behavior_rejected("실행 기록 사례 ID 불일치")

    def test_protected_literal_deletion_rejected(self):
        cases_path, case_set = self.read_json("tests/cases/2.0.1.json")
        target = next(case for case in case_set["cases"] if case["protection"]["literals"])
        case_id = target["id"]
        literal = target["protection"]["literals"][0]
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        self.assertIn(literal, evidence["outputs"][case_id])
        evidence["outputs"][case_id] = evidence["outputs"][case_id].replace(literal, "", 1)
        self.write_json(evidence_path, evidence)
        self.rebind_audit_to_evidence(case_id)
        self.assert_behavior_rejected("보호 literal 출현 횟수 불일치")

    def test_protected_literal_duplication_rejected(self):
        cases_path, case_set = self.read_json("tests/cases/2.0.1.json")
        target = next(case for case in case_set["cases"] if case["protection"]["literals"])
        case_id = target["id"]
        literal = target["protection"]["literals"][0]
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        evidence["outputs"][case_id] += " " + literal
        self.write_json(evidence_path, evidence)
        self.rebind_audit_to_evidence(case_id)
        self.assert_behavior_rejected("보호 literal 출현 횟수 불일치")

    def test_same_executor_and_auditor_rejected(self):
        evidence_path, evidence = self.read_json("tests/evidence/2.0.1/final.json")
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        evidence["execution"]["agent"] = audit["auditor"]["agent"]
        self.write_json(evidence_path, evidence)
        self.rebind_audit_to_evidence()
        self.assert_behavior_rejected("실행자와 감사자")

    def test_failed_case_with_passing_overall_rejected(self):
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        result = audit["results"]["R01"]
        first_dimension = next(iter(result["dimensions"]))
        result["dimensions"][first_dimension] = "fail"
        result["result"] = "fail"
        audit["overall"] = "pass"
        self.write_json(audit_path, audit)
        self.assert_behavior_rejected("overall")

    def test_missing_audit_dimension_rejected(self):
        audit_path, audit = self.read_json("tests/evidence/2.0.1/audit.json")
        audit["results"]["R01"]["dimensions"].pop("terminologyJudgment")
        self.write_json(audit_path, audit)
        self.assert_behavior_rejected("dimensions 이름 불일치")

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
