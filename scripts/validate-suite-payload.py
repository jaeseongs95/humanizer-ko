#!/usr/bin/env python3
"""agent-governance-suite에 복사할 Humanizer KO Skill payload를 검사한다."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "humanizer-ko"
SOURCE_ROOT = ROOT / "skills" / SKILL_NAME
TARGET_ROOT = Path("skills") / SKILL_NAME

REQUIRED_FILES = {
    Path("SKILL.md"),
    Path("LICENSE"),
    Path("THIRD_PARTY_NOTICES.md"),
    Path("agents/openai.yaml"),
}
ALLOWED_TOP_LEVEL_FILES = {
    "SKILL.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
}
ALLOWED_RESOURCE_DIRS = {"agents", "assets", "references", "scripts"}
REPOSITORY_ONLY_NAMES = {
    ".git",
    ".github",
    ".codex-plugin",
    ".claude-plugin",
    "AGENTS.md",
    "AGENTS.override.md",
    "README.md",
    "tests",
    "__pycache__",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def collect_payload() -> list[Path]:
    if not SOURCE_ROOT.is_dir():
        fail(f"Skill 원본 디렉터리가 없습니다: {SOURCE_ROOT.relative_to(ROOT)}")

    files: list[Path] = []
    for path in sorted(SOURCE_ROOT.rglob("*")):
        relative = path.relative_to(SOURCE_ROOT)
        if path.is_symlink():
            fail(f"payload에는 심볼릭 링크를 둘 수 없습니다: {relative.as_posix()}")
        if any(part in REPOSITORY_ONLY_NAMES for part in relative.parts):
            fail(f"저장소 전용 파일을 Skill payload에서 제거하세요: {relative.as_posix()}")
        if path.is_dir():
            continue
        if len(relative.parts) == 1:
            if relative.name not in ALLOWED_TOP_LEVEL_FILES:
                fail(f"Skill 최상위에 허용되지 않은 파일이 있습니다: {relative.as_posix()}")
        elif relative.parts[0] not in ALLOWED_RESOURCE_DIRS:
            fail(f"Skill 리소스 디렉터리를 확인하세요: {relative.as_posix()}")
        if relative.parts[0] == "agents" and relative != Path("agents/openai.yaml"):
            fail(f"agents에는 openai.yaml만 포함하세요: {relative.as_posix()}")
        if path.suffix in {".pyc", ".pyo"}:
            fail(f"생성된 Python 파일을 payload에서 제거하세요: {relative.as_posix()}")
        files.append(relative)

    missing = sorted(REQUIRED_FILES - set(files))
    if missing:
        fail("필수 payload 파일이 없습니다: " + ", ".join(path.as_posix() for path in missing))
    return files


def validate_frontmatter() -> None:
    skill = (SOURCE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata_match = re.match(r"\A---\n(.*?)\n---\n", skill, re.DOTALL)
    if metadata_match is None:
        fail("SKILL.md는 YAML frontmatter로 시작해야 합니다.")
    name_match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", metadata_match.group(1))
    if name_match is None or name_match.group(1) != SKILL_NAME:
        fail(f"Skill 디렉터리와 frontmatter name을 {SKILL_NAME}로 일치시키세요.")


def validate_local_links(files: list[Path]) -> None:
    root = SOURCE_ROOT.resolve()
    for relative in files:
        if relative.suffix.lower() != ".md":
            continue
        document = (SOURCE_ROOT / relative).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", document):
            target = target.strip()
            if not target or target.startswith("#") or "://" in target or target.startswith("mailto:"):
                continue
            link_path = target.split("#", 1)[0]
            resolved = ((SOURCE_ROOT / relative).parent / link_path).resolve()
            if not resolved.is_relative_to(root):
                fail(f"payload 밖을 가리키는 로컬 링크가 있습니다: {relative.as_posix()} -> {target}")
            if not resolved.is_file():
                fail(f"payload 안의 로컬 링크 대상이 없습니다: {relative.as_posix()} -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list",
        action="store_true",
        help="검증 후 source -> agent-governance-suite target 경로를 출력한다.",
    )
    arguments = parser.parse_args()

    files = collect_payload()
    validate_frontmatter()
    validate_local_links(files)

    if arguments.list:
        for relative in files:
            source = Path("skills") / SKILL_NAME / relative
            target = TARGET_ROOT / relative
            print(f"{source.as_posix()} -> {target.as_posix()}")
    else:
        print(
            f"agent-governance-suite payload 검증 완료: "
            f"{TARGET_ROOT.as_posix()} ({len(files)}개 파일)"
        )


if __name__ == "__main__":
    main()
