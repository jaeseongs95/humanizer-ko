#!/usr/bin/env python3
"""기록된 행동 출력의 문자 보호를 재검증한다. 문장 의미·자연스러움은 채점하지 않는다."""

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PATTERNS = {
    "인용": r"“[^”]+”",
    "인라인 코드·경로": r"(?<!`)`(?!`)[^`\r\n]+`(?!`)",
    # URL 뒤 조사까지 붙었으면 다른 대상으로 검출한다. 부분 문자열 포함만 보지 않는다.
    "URL": r"https?://[^\s)\]>]+",
}


def normalized(text):
    return text.replace("\r\n", "\n")


def matches(text, pattern):
    return re.findall(pattern, normalized(text), re.MULTILINE)


def source_case(document, case_id):
    found = re.search(
        rf"(?ms)^## {case_id} .*?^입력: (.*?)\n\n조건:", document
    )
    if not found:
        raise ValueError(f"{case_id} 입력이 없습니다.")
    return found.group(1)


def compare(source, output, patterns, label, errors):
    count = 0
    for name, pattern in patterns.items():
        before, after = matches(source, pattern), matches(output, pattern)
        if not before:
            errors.append(f"{label}: 원문에 {name} 보호 구간이 없어 검증할 수 없습니다.")
        elif before != after:
            errors.append(f"{label}: {name} 불일치: {before!r} != {after!r}")
        else:
            count += 1
    return count


def check(evidence, holdout):
    errors, count = [], 0
    source = source_case(holdout, "H04")
    mixed = source_case(holdout, "H06")
    english = (
        "This release keeps the Retry-After header unchanged.",
        "The rollback command is `deploy --rollback`.",
    )
    for number, run in enumerate(evidence["runs"], 1):
        output = run["outputs"]
        count += compare(source, output["H04"], PATTERNS, f"실행 {number}/H04", errors)
        count += compare(mixed, output["H06"], {"인라인 코드": PATTERNS["인라인 코드·경로"]},
                         f"실행 {number}/H06", errors)
        for sentence in english:
            if sentence not in output["H06"]:
                errors.append(f"실행 {number}/H06: 영어 문장 변경: {sentence}")
            else:
                count += 1

    mode = evidence["modes"]
    file_patterns = {
        **PATTERNS,
        "YAML": r"\A---\n[\s\S]*?\n---",
        "코드 블록": r"^```[^\n]*\n[\s\S]*?^```",
        "표": r"^\|.*$",
        "영어 문단": r"^The Retry-After header remains unchanged\.$",
    }
    count += compare(mode["source"], mode["edited"], file_patterns, "파일 편집", errors)
    return count, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?", type=Path,
                        help="명시하면 해당 과거 기록만 검사한다. 생략하면 현재 지침과 최종 기록의 일치도 검사한다.")
    args = parser.parse_args()
    path = args.evidence or ROOT / "tests/evidence/1.0.2/final.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    snapshot = normalized(evidence["skill"])
    if hashlib.sha256(snapshot.encode("utf-8")).hexdigest().upper() != evidence["skillSha256"]:
        raise SystemExit("기록된 지침 스냅샷과 해시가 일치하지 않습니다.")
    if args.evidence is None and snapshot != normalized((ROOT / "SKILL.md").read_text(encoding="utf-8")):
        raise SystemExit("현재 지침이 최종 검증 스냅샷과 다릅니다. 행동 검증 기록을 갱신하세요.")
    holdout = (ROOT / "tests/HOLDOUT_CASES.md").read_text(encoding="utf-8")
    count, errors = check(evidence, holdout)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"보호 구간 비교 {count}개 통과. 의미·격식·자연스러움은 별도 감사 대상입니다.")


if __name__ == "__main__":
    main()
