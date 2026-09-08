#!/usr/bin/env python3
"""Humanizer KO 패키지의 공유 식별자, 버전, 패턴과 고지를 검사한다."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_NAME = "humanizer-ko"
EXPECTED_PATTERN_COUNT = 25
UPSTREAM_COMMIT = "9862685f575c65a8247f90369951df1b3416e3d6"


def read_package_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"파일을 읽을 수 없습니다: {path.relative_to(ROOT)}: {error}")


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(read_package_file(path))
    except json.JSONDecodeError as error:
        raise SystemExit(f"JSON 형식을 수정하세요: {path.relative_to(ROOT)}: {error}")
    if not isinstance(value, dict):
        raise SystemExit(f"JSON 최상위 값은 객체여야 합니다: {path.relative_to(ROOT)}")
    return value


def require_match(match: re.Match[str] | None, message: str) -> re.Match[str]:
    if match is None:
        raise SystemExit(message)
    return match


def read_yaml_section(document: str, section_name: str) -> str:
    """간단한 2단계 YAML에서 지정한 최상위 섹션의 들여쓴 본문을 반환한다."""
    lines = document.splitlines()
    markers = [index for index, line in enumerate(lines) if line == f"{section_name}:"]
    if len(markers) != 1:
        raise SystemExit(f"openai.yaml에 최상위 {section_name}: 섹션을 하나만 두세요.")
    section: list[str] = []
    for line in lines[markers[0] + 1:]:
        if line and not line[0].isspace():
            break
        section.append(line)
    return "\n".join(section)


SKILL_PATH = ROOT / "skills" / EXPECTED_NAME / "SKILL.md"
SKILL = read_package_file(SKILL_PATH)
README = read_package_file(ROOT / "README.md")
LICENSE = read_package_file(ROOT / "LICENSE")
NOTICES = read_package_file(ROOT / "THIRD_PARTY_NOTICES.md")
INSTALLED_LICENSE = read_package_file(SKILL_PATH.parent / "LICENSE")
INSTALLED_NOTICES = read_package_file(SKILL_PATH.parent / "THIRD_PARTY_NOTICES.md")
OPENAI = read_package_file(SKILL_PATH.parent / "agents" / "openai.yaml")
HOST_INSTRUCTIONS = {
    "ChatGPT": read_package_file(ROOT / "examples" / "CHATGPT.custom-instructions.humanizer-ko.md"),
    "Codex": read_package_file(ROOT / "examples" / "AGENTS.humanizer-ko.md"),
    "Claude": read_package_file(ROOT / "examples" / "CLAUDE.humanizer-ko.md"),
}
CODEX_PLUGIN = read_json(ROOT / ".codex-plugin" / "plugin.json")
CLAUDE_PLUGIN = read_json(ROOT / ".claude-plugin" / "plugin.json")
MARKETPLACE = read_json(ROOT / ".claude-plugin" / "marketplace.json")

yaml_metadata = require_match(
    re.match(r"\A---\n(.*?)\n---\n", SKILL, re.DOTALL),
    "SKILL.md는 YAML 메타데이터로 시작해야 합니다.",
).group(1)

for unsupported_field in ("version:", "compatibility:", "allowed-tools:"):
    if re.search(rf"(?m)^{re.escape(unsupported_field)}", yaml_metadata):
        raise SystemExit(f"지원하지 않는 YAML 필드를 제거하세요: {unsupported_field[:-1]}")

skill_description = require_match(
    re.search(r"(?m)^description:\s*(\S.+)$", yaml_metadata),
    "SKILL.md에 비어 있지 않은 description을 추가하세요.",
).group(1)
for required_text in ("완성형 한국어 산문", "작성", "편집", "일반 질문", "짧은 확인", "영어 전용"):
    if required_text not in skill_description:
        raise SystemExit(f"SKILL.md description에 호출 경계를 추가하세요: {required_text}")

skill_name = require_match(
    re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", yaml_metadata),
    "SKILL.md에 유효한 name을 추가하세요.",
).group(1)
if skill_name != EXPECTED_NAME:
    raise SystemExit(f"Skill 이름은 {EXPECTED_NAME}여야 합니다: {skill_name}")

skill_license = require_match(
    re.search(r"(?m)^license:\s*([^\s]+)\s*$", yaml_metadata),
    "SKILL.md에 license를 추가하세요.",
).group(1)
if skill_license != "MIT":
    raise SystemExit(f"Skill 라이선스는 MIT여야 합니다: {skill_license}")

skill_version = require_match(
    re.search(r'(?m)^\s+version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)["\']?\s*$', yaml_metadata),
    "SKILL.md의 metadata.version에 세 부분 버전을 추가하세요.",
).group(1)
readme_version = require_match(
    re.search(r"(?m)^- \*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*", README),
    "README.md에 버전 기록을 추가하세요.",
).group(1)
package_versions = {
    skill_version,
    readme_version,
    str(CODEX_PLUGIN.get("version", "")),
    str(CLAUDE_PLUGIN.get("version", "")),
}
if len(package_versions) != 1:
    raise SystemExit(f"모든 패키지 버전을 일치시키세요: {sorted(package_versions)}")

if CODEX_PLUGIN.get("name") != EXPECTED_NAME:
    raise SystemExit("Codex 플러그인 이름을 humanizer-ko로 설정하세요.")
if CODEX_PLUGIN.get("skills") != "./skills/":
    raise SystemExit("Codex 플러그인의 skills는 ./skills/를 가리켜야 합니다.")
if CODEX_PLUGIN.get("license") != "MIT":
    raise SystemExit("Codex 플러그인 라이선스를 MIT로 설정하세요.")
for unsupported_component in ("apps", "mcpServers", "hooks"):
    if unsupported_component in CODEX_PLUGIN:
        raise SystemExit(f"현재 패키지에 없는 Codex 구성 요소를 제거하세요: {unsupported_component}")

codex_interface = CODEX_PLUGIN.get("interface")
if not isinstance(codex_interface, dict):
    raise SystemExit("Codex 플러그인에 interface 객체를 추가하세요.")
required_interface = {
    "displayName": "Humanizer KO",
    "developerName": "jaeseongs95",
    "category": "Productivity",
    "capabilities": ["Read", "Write"],
}
for field, expected in required_interface.items():
    if codex_interface.get(field) != expected:
        raise SystemExit(f"Codex interface.{field} 값을 확인하세요.")
for field in ("shortDescription", "longDescription"):
    if not isinstance(codex_interface.get(field), str) or not codex_interface[field].strip():
        raise SystemExit(f"Codex interface.{field}에 설명을 추가하세요.")
starter_prompts = codex_interface.get("defaultPrompt")
if not isinstance(starter_prompts, list) or not starter_prompts or not all(
    isinstance(prompt, str) and prompt.strip() for prompt in starter_prompts
):
    raise SystemExit("Codex interface.defaultPrompt에 시작 프롬프트를 추가하세요.")

if CLAUDE_PLUGIN.get("name") != EXPECTED_NAME:
    raise SystemExit("Claude 플러그인 이름을 humanizer-ko로 설정하세요.")
if CLAUDE_PLUGIN.get("skills") != ["./skills/humanizer-ko"]:
    raise SystemExit("Claude 플러그인의 skills는 ./skills/humanizer-ko를 가리켜야 합니다.")
if CLAUDE_PLUGIN.get("license") != "MIT":
    raise SystemExit("Claude 플러그인 라이선스를 MIT로 설정하세요.")
for field in ("description", "author", "homepage", "repository", "license", "keywords"):
    if CLAUDE_PLUGIN.get(field) != CODEX_PLUGIN.get(field):
        raise SystemExit(f"Codex와 Claude 플러그인의 {field} 값을 일치시키세요.")

if MARKETPLACE.get("name") != EXPECTED_NAME:
    raise SystemExit("Claude marketplace 이름을 humanizer-ko로 설정하세요.")
marketplace_plugins = MARKETPLACE.get("plugins")
if not isinstance(marketplace_plugins, list) or len(marketplace_plugins) != 1:
    raise SystemExit("Claude marketplace에는 플러그인 항목이 하나 있어야 합니다.")
marketplace_plugin = marketplace_plugins[0]
if not isinstance(marketplace_plugin, dict) or marketplace_plugin.get("name") != EXPECTED_NAME:
    raise SystemExit("Claude marketplace 플러그인 이름을 humanizer-ko로 설정하세요.")
if marketplace_plugin.get("source") != "./" or marketplace_plugin.get("license") != "MIT":
    raise SystemExit("Claude marketplace source와 license를 확인하세요.")
if marketplace_plugin.get("description") != CLAUDE_PLUGIN.get("description"):
    raise SystemExit("플러그인과 marketplace의 설명을 일치시키세요.")
if MARKETPLACE.get("owner") != CLAUDE_PLUGIN.get("author"):
    raise SystemExit("플러그인과 marketplace의 한국어판 관리자를 일치시키세요.")

skill_files = {path.relative_to(ROOT) for path in ROOT.rglob("SKILL.md")}
expected_skill_path = Path("skills") / EXPECTED_NAME / "SKILL.md"
if SKILL_PATH.is_symlink() or skill_files != {expected_skill_path}:
    raise SystemExit("skills/humanizer-ko에 일반 파일 SKILL.md 하나만 두세요.")

pattern_numbers = [
    int(number) for number in re.findall(r"(?m)^### ([0-9]+)\. ", SKILL)
]
expected_numbers = list(range(1, EXPECTED_PATTERN_COUNT + 1))
if pattern_numbers != expected_numbers:
    raise SystemExit(f"SKILL.md 패턴 번호를 1부터 25까지 이어서 작성하세요: {pattern_numbers}")

example_count = len(re.findall(r"(?m)^예: ", SKILL))
if example_count != EXPECTED_PATTERN_COUNT:
    raise SystemExit(f"각 패턴에 새 한국어 예시를 하나씩 작성하세요: {example_count}개")

readme_numbers = [
    int(number) for number in re.findall(r"(?m)^\| ([0-9]+) \|", README)
]
if readme_numbers != expected_numbers:
    raise SystemExit(f"README 표에 패턴 1부터 25까지 한 번씩 나열하세요: {readme_numbers}")
if "## 25개 패턴" not in README:
    raise SystemExit("README 패턴 제목은 '## 25개 패턴'이어야 합니다.")
if len(SKILL.splitlines()) > 400:
    raise SystemExit("SKILL.md는 400줄 이하여야 합니다.")

for category in "ABCDE":
    if f"## {category}." not in SKILL:
        raise SystemExit(f"SKILL.md에 {category} 범주를 추가하세요.")

openai_interface = read_yaml_section(OPENAI, "interface")
openai_policy = read_yaml_section(OPENAI, "policy")
default_prompt = require_match(
    re.search(r'(?m)^\s+default_prompt:\s*"([^"]+)"\s*$', openai_interface),
    "skills/humanizer-ko/agents/openai.yaml에 따옴표로 감싼 default_prompt를 추가하세요.",
).group(1)
if default_prompt != "$humanizer-ko를 사용해 이 글의 사실은 유지하면서 자연스러운 한국어로 다듬어 주세요.":
    raise SystemExit("OpenAI 기본 프롬프트를 한국어판 호출 문구와 일치시키세요.")
if not re.search(r"(?m)^\s+allow_implicit_invocation:\s*true\s*$", openai_policy):
    raise SystemExit("한국어판의 자동 Skill 선택을 true로 유지하세요.")

short_description = require_match(
    re.search(r'(?m)^\s+short_description:\s*"([^"]+)"\s*$', openai_interface),
    "skills/humanizer-ko/agents/openai.yaml에 short_description을 추가하세요.",
).group(1)
if not 25 <= len(short_description) <= 64:
    raise SystemExit("OpenAI short_description은 25~64자여야 합니다.")

shared_instruction_requirements = (
    "## 기본 한국어 문체",
    "README·메일·보고서·안내문·여러 문단의 설명문",
    "일반 질문, 진행 상황과 짧은 확인 답변",
    "새 글은 본래 작업에 필요한 조사와 내용 작성을 먼저 수행",
    "영어 전용 작업에는 한국어 편집을 적용하지 않는다",
)
host_requirements = {
    "ChatGPT": ("## 한국어 산문 작성·편집의 스킬 적용", "`@humanizer-ko`"),
    "Codex": (
        "## 한국어 산문 작성·편집의 스킬 적용",
        "`$humanizer-ko`",
        "`humanizer-ko` 스킬을 읽고 사용한다",
        "스킬 파일을 읽기 전에",
        "연도·월·일·시각",
    ),
    "Claude": ("## 한국어 산문 작성·편집의 Skill 적용", "`/humanizer-ko:humanizer-ko`"),
}
for host, instructions in HOST_INSTRUCTIONS.items():
    for required_text in (*shared_instruction_requirements, *host_requirements[host]):
        if required_text not in instructions:
            raise SystemExit(f"{host} 적용 예시에 필수 규칙을 추가하세요: {required_text}")

readme_requirements = (
    "codex plugin marketplace add jaeseongs95/humanizer-ko",
    "codex plugin add humanizer-ko@humanizer-ko",
    "`@humanizer-ko`",
    "`$humanizer-ko`",
    "`/humanizer-ko:humanizer-ko`",
    "skills/humanizer-ko/SKILL.md",
)
for required_text in readme_requirements:
    if required_text not in README:
        raise SystemExit(f"README에 설치·호출 정보를 추가하세요: {required_text}")

license_requirements = ("MIT License", "Copyright (c) 2025 Siqi Chen")
for required_text in license_requirements:
    if required_text not in LICENSE:
        raise SystemExit(f"원본 MIT 고지를 LICENSE에 보존하세요: {required_text}")

# Windows 체크아웃의 CRLF만 정규화하고 원본 v3.0.0 LICENSE 전문을 비교한다.
if hashlib.sha256(LICENSE.encode("utf-8")).hexdigest() != "4ac4810254ab36d45419141aeb8e69bf50652cfafe5b2dab947d06d44e5cbf96":
    raise SystemExit("LICENSE의 원본 MIT 전문이 변경되었습니다.")
if INSTALLED_LICENSE != LICENSE:
    raise SystemExit("독립형 Skill의 LICENSE를 루트 원본과 일치시키세요.")
if INSTALLED_NOTICES != NOTICES:
    raise SystemExit("독립형 Skill의 THIRD_PARTY_NOTICES.md를 루트 원본과 일치시키세요.")

notice_requirements = (
    UPSTREAM_COMMIT,
    "https://github.com/blader/humanizer",
    "CC BY-SA 4.0",
    "비공식",
    "2026-09-08",
)
for required_text in notice_requirements:
    if required_text not in NOTICES:
        raise SystemExit(f"THIRD_PARTY_NOTICES.md에 필수 고지를 추가하세요: {required_text}")

# 이 검사는 출처 고지의 존재만 확인하며 저작권 판단이나 행동 품질을 증명하지 않는다.
for target in re.findall(r"\]\(([^)]+)\)", README):
    if "://" not in target and not target.startswith("#") and not (ROOT / target.split("#")[0]).is_file():
        raise SystemExit(f"README의 로컬 링크 대상이 없습니다: {target}")

print(
    f"Humanizer KO 패키지 v{skill_version} 검증 완료: "
    f"패턴 {EXPECTED_PATTERN_COUNT}개, 라이선스 및 제3자 고지 확인"
)
