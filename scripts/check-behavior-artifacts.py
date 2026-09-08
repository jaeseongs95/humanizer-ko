#!/usr/bin/env python3
"""행동 검증 기록의 정본 결속과 문자 보존을 확인한다.

의미·격식·자연스러움과 특정 표현의 정답 여부는 자동 판정하지 않는다.
그 판정은 독립 감사 기록에 맡기고, 이 스크립트는 입력·출력·감사 기록이
검토된 바로 그 파일과 문자열에 결속돼 있는지만 재현 가능하게 검사한다.
"""

import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CURRENT_SUITE = "humanizer-ko/2.0.1"
CURRENT_PATHS = {
    "skill": "skills/humanizer-ko/SKILL.md",
    "caseSet": "tests/cases/2.0.1.json",
    "protocol": "tests/EVALUATION_PROTOCOL.md",
    "evidence": "tests/evidence/2.0.1/final.json",
    "audit": "tests/evidence/2.0.1/audit.json",
}
CAPTURE_PATTERNS = {
    "directQuote": r"“[^”\r\n]*”|‘[^’\r\n]*’",
    "inlineCode": r"(?<!`)`(?!`)[^`\r\n]+`(?!`)",
    "url": r"https?://[^\s)\]>]+",
    # 표시 문구는 산문이므로 바꿀 수 있지만 링크 대상은 기계 참조로 보호한다.
    "markdownLink": r"!?\[[^\]\r\n]+\]\(([^\s)]+)\)",
    "englishSentence": r"(?<![A-Za-z])[A-Z][A-Za-z0-9 `',\-]+[.!?]",
    "number": r"\d+(?:[.,:/~\-]\d+)*",
}
LEGACY_PATTERNS = {
    "인용": CAPTURE_PATTERNS["directQuote"],
    "인라인 코드·경로": CAPTURE_PATTERNS["inlineCode"],
    "URL": CAPTURE_PATTERNS["url"],
}
ALLOWED_RESULTS = {"pass", "fail", "uncertain", "notApplicable"}
SCHEMA2_CAPTURE_KINDS = {
    "directQuote", "inlineCode", "url", "markdownLink", "englishSentence"
}
REQUIRED_DIMENSIONS = {
    "meaningPreservation",
    "requestCompliance",
    "naturalness",
    "terminologyJudgment",
}


def normalized(text):
    """운영체제 줄바꿈 차이를 제거한 정본 문자열을 반환한다."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(text):
    return hashlib.sha256(normalized(text).encode("utf-8")).hexdigest()


def read_text(path):
    return path.read_text(encoding="utf-8")


def matches(text, pattern):
    return re.findall(pattern, normalized(text), re.MULTILINE)


def source_case(document, case_id):
    found = re.search(rf"(?ms)^## {case_id} .*?^입력: (.*?)\n\n조건:", document)
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


def check_legacy(evidence, holdout):
    errors, count = [], 0
    source = source_case(holdout, "H04")
    mixed = source_case(holdout, "H06")
    english = (
        "This release keeps the Retry-After header unchanged.",
        "The rollback command is `deploy --rollback`.",
    )
    for number, run in enumerate(evidence["runs"], 1):
        output = run["outputs"]
        count += compare(source, output["H04"], LEGACY_PATTERNS,
                         f"실행 {number}/H04", errors)
        count += compare(mixed, output["H06"],
                         {"인라인 코드": LEGACY_PATTERNS["인라인 코드·경로"]},
                         f"실행 {number}/H06", errors)
        for sentence in english:
            if sentence not in output["H06"]:
                errors.append(f"실행 {number}/H06: 영어 문장 변경: {sentence}")
            else:
                count += 1

    mode = evidence["modes"]
    file_patterns = {
        **LEGACY_PATTERNS,
        "YAML": r"\A---\n[\s\S]*?\n---",
        "코드 블록": r"^```[^\n]*\n[\s\S]*?^```",
        "표": r"^\|.*$",
        "영어 문단": r"^The Retry-After header remains unchanged\.$",
    }
    count += compare(mode["source"], mode["edited"], file_patterns,
                     "파일 편집", errors)
    return count, errors


def check_schema2(evidence):
    """과거 schemaVersion 2 기록 내부의 구조와 보호 문자열만 검사한다.

    이 형식은 Skill 본문 스냅샷과 독립 감사 결속을 담지 않았으므로 기록된
    skillSha256를 현재 Skill과 비교하지 않는다. 현재 상태의 독립 검증으로
    승격하지 않고, 당시 source/output 쌍에서 재현 가능한 범위만 확인한다.
    """
    errors, count = [], 0
    validate_hash(evidence.get("skillSha256"), "schemaVersion 2 skillSha256")
    sources = require_object(evidence.get("sources"), "schemaVersion 2 sources")
    outputs = require_object(evidence.get("outputs"), "schemaVersion 2 outputs")
    if not sources:
        errors.append("schemaVersion 2 sources가 비어 있습니다.")
    if set(sources) != set(outputs):
        missing = sorted(set(sources) - set(outputs))
        extra = sorted(set(outputs) - set(sources))
        errors.append(f"schemaVersion 2 사례 ID 불일치: 누락={missing}, 초과={extra}")
    seen_sources = set()
    for case_id in sorted(set(sources) & set(outputs)):
        source, output = sources[case_id], outputs[case_id]
        if not isinstance(source, str) or not source:
            errors.append(f"schemaVersion 2 {case_id}: source가 비어 있지 않은 문자열이 아닙니다.")
            continue
        if source in seen_sources:
            errors.append(f"schemaVersion 2 {case_id}: source가 중복됩니다.")
        seen_sources.add(source)
        if not isinstance(output, str):
            errors.append(f"schemaVersion 2 {case_id}: output이 문자열이 아닙니다.")
            continue
        for kind in sorted(SCHEMA2_CAPTURE_KINDS):
            pattern = CAPTURE_PATTERNS[kind]
            before = Counter(matches(source, pattern))
            if not before:
                continue
            after = Counter(matches(output, pattern))
            if before != after:
                errors.append(
                    f"schemaVersion 2 {case_id}: {kind} multiset 불일치: {before!r} != {after!r}"
                )
            else:
                count += 1
    return count, errors


def require_object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: 객체여야 합니다.")
    return value


def require_string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}: 비어 있지 않은 문자열이어야 합니다.")
    return value


def validate_hash(value, label):
    value = require_string(value, label)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError(f"{label}: SHA-256 형식이 아닙니다.")
    return value.lower()


def load_current_cases(path):
    case_set = require_object(json.loads(read_text(path)), "사례 정본")
    if case_set.get("schemaVersion") != 1:
        raise ValueError("사례 정본의 schemaVersion은 1이어야 합니다.")
    if case_set.get("suiteId") != CURRENT_SUITE:
        raise ValueError(f"사례 정본의 suiteId는 {CURRENT_SUITE!r}여야 합니다.")
    raw_cases = case_set.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("사례 정본의 cases는 비어 있지 않은 배열이어야 합니다.")

    cases, inputs = {}, set()
    for index, raw_case in enumerate(raw_cases, 1):
        case = require_object(raw_case, f"사례 {index}")
        case_id = require_string(case.get("id"), f"사례 {index}.id")
        criteria_id = require_string(case.get("criteriaId"), f"{case_id}.criteriaId")
        request = require_string(case.get("request"), f"{case_id}.request")
        prompt = require_string(case.get("input"), f"{case_id}.input")
        if case_id in cases:
            raise ValueError(f"사례 ID가 중복됩니다: {case_id}")
        if prompt in inputs:
            raise ValueError(f"사례 원문이 중복됩니다: {case_id}")
        protection = require_object(case.get("protection"), f"{case_id}.protection")
        kinds = protection.get("captureKinds")
        literals = protection.get("literals")
        if not isinstance(kinds, list) or not all(isinstance(v, str) for v in kinds):
            raise ValueError(f"{case_id}.protection.captureKinds는 문자열 배열이어야 합니다.")
        if len(kinds) != len(set(kinds)):
            raise ValueError(f"{case_id}: captureKinds가 중복됩니다.")
        unknown = sorted(set(kinds) - set(CAPTURE_PATTERNS))
        if unknown:
            raise ValueError(f"{case_id}: 알 수 없는 captureKinds: {unknown}")
        if not isinstance(literals, list) or not all(isinstance(v, str) and v for v in literals):
            raise ValueError(f"{case_id}.protection.literals는 비어 있지 않은 문자열의 배열이어야 합니다.")
        if len(literals) != len(set(literals)):
            raise ValueError(f"{case_id}: 보호 literal이 중복 선언됐습니다.")
        for literal in literals:
            if prompt.count(literal) == 0:
                raise ValueError(f"{case_id}: 보호 literal이 원문에 없습니다: {literal!r}")
        for kind in kinds:
            if not matches(prompt, CAPTURE_PATTERNS[kind]):
                raise ValueError(f"{case_id}: {kind} 보호 대상을 원문에서 찾지 못했습니다.")
        cases[case_id] = {
            "criteriaId": criteria_id,
            "request": request,
            "input": prompt,
            "captureKinds": kinds,
            "literals": literals,
        }
        inputs.add(prompt)
    return case_set, cases


def protocol_criteria(document):
    ids = set()
    for line in normalized(document).splitlines():
        found = re.match(r"^\|\s*([A-Za-z]+\d+)\s*\|", line)
        if found:
            ids.add(found.group(1))
    return ids


def verify_binding(bindings, name, expected_path, actual_path):
    binding = require_object(bindings.get(name), f"bindings.{name}")
    if binding.get("path") != expected_path:
        raise ValueError(
            f"bindings.{name}.path는 고정 경로 {expected_path!r}여야 합니다."
        )
    expected_hash = sha256_text(read_text(actual_path))
    recorded_hash = validate_hash(binding.get("sha256"), f"bindings.{name}.sha256")
    if recorded_hash != expected_hash:
        raise ValueError(f"bindings.{name}: 현재 파일의 LF 정규화 SHA-256과 다릅니다.")
    return recorded_hash


def expected_result(dimensions):
    values = list(dimensions.values())
    if "fail" in values:
        return "fail"
    if "uncertain" in values:
        return "uncertain"
    if values and all(value == "notApplicable" for value in values):
        return "notApplicable"
    return "pass"


def expected_overall(results):
    values = [result["result"] for result in results.values()]
    if "fail" in values:
        return "fail"
    if "uncertain" in values:
        return "uncertain"
    if values and all(value == "notApplicable" for value in values):
        return "notApplicable"
    return "pass"


def check_current(evidence_path):
    errors, count = [], 0
    paths = {key: ROOT / value for key, value in CURRENT_PATHS.items()}
    evidence = require_object(json.loads(read_text(evidence_path)), "실행 기록")
    if evidence_path.resolve() != paths["evidence"].resolve():
        raise ValueError("schemaVersion 3 실행 기록은 고정 evidence 경로에서만 검사합니다.")
    if evidence.get("schemaVersion") != 3:
        raise ValueError("현재 기본 실행 기록의 schemaVersion은 3이어야 합니다.")
    if evidence.get("artifactKind") != "behavior-execution":
        raise ValueError("실행 기록의 artifactKind는 'behavior-execution'이어야 합니다.")
    if evidence.get("suiteId") != CURRENT_SUITE:
        raise ValueError(f"실행 기록의 suiteId는 {CURRENT_SUITE!r}여야 합니다.")
    if "sources" in evidence:
        raise ValueError("실행 기록에 원문 복사본 sources를 둘 수 없습니다. 사례 정본을 참조하세요.")

    _, cases = load_current_cases(paths["caseSet"])
    protocol = read_text(paths["protocol"])
    criteria = protocol_criteria(protocol)
    for case_id, case in cases.items():
        if case["criteriaId"] not in criteria:
            errors.append(
                f"{case_id}: criteriaId {case['criteriaId']!r}가 평가 규약 표에 없습니다."
            )

    bindings = require_object(evidence.get("bindings"), "실행 기록 bindings")
    bound_hashes = {
        "skillSha256": verify_binding(bindings, "skill", CURRENT_PATHS["skill"], paths["skill"]),
        "caseSetSha256": verify_binding(bindings, "caseSet", CURRENT_PATHS["caseSet"], paths["caseSet"]),
        "protocolSha256": verify_binding(bindings, "protocol", CURRENT_PATHS["protocol"], paths["protocol"]),
    }
    execution = require_object(evidence.get("execution"), "execution")
    executor_agent = require_string(execution.get("agent"), "execution.agent")
    outputs = require_object(evidence.get("outputs"), "outputs")
    if set(outputs) != set(cases):
        missing = sorted(set(cases) - set(outputs))
        extra = sorted(set(outputs) - set(cases))
        errors.append(f"실행 기록 사례 ID 불일치: 누락={missing}, 초과={extra}")

    for case_id in sorted(set(cases) & set(outputs)):
        output = outputs[case_id]
        if not isinstance(output, str):
            errors.append(f"{case_id}: 출력은 문자열이어야 합니다.")
            continue
        case = cases[case_id]
        source = case["input"]
        for kind in case["captureKinds"]:
            before = Counter(matches(source, CAPTURE_PATTERNS[kind]))
            after = Counter(matches(output, CAPTURE_PATTERNS[kind]))
            if before != after:
                errors.append(f"{case_id}: {kind} multiset 불일치: {before!r} != {after!r}")
            else:
                count += 1
        for literal in case["literals"]:
            before, after = source.count(literal), output.count(literal)
            if before != after:
                errors.append(
                    f"{case_id}: 보호 literal 출현 횟수 불일치 {literal!r}: {before} != {after}"
                )
            else:
                count += 1

    audit_path = paths["audit"]
    audit = require_object(json.loads(read_text(audit_path)), "감사 기록")
    if audit.get("schemaVersion") != 2:
        raise ValueError("현재 감사 기록의 schemaVersion은 2여야 합니다.")
    if audit.get("artifactKind") != "behavior-audit":
        raise ValueError("감사 기록의 artifactKind는 'behavior-audit'이어야 합니다.")
    if audit.get("suiteId") != CURRENT_SUITE:
        raise ValueError(f"감사 기록의 suiteId는 {CURRENT_SUITE!r}여야 합니다.")
    audit_bindings = require_object(audit.get("bindings"), "감사 기록 bindings")
    if audit_bindings.get("evidencePath") != CURRENT_PATHS["evidence"]:
        errors.append("감사 기록의 evidencePath가 고정 실행 기록 경로와 다릅니다.")
    evidence_hash = validate_hash(audit_bindings.get("evidenceSha256"),
                                  "audit.bindings.evidenceSha256")
    if evidence_hash != sha256_text(read_text(evidence_path)):
        errors.append("감사 기록의 evidenceSha256가 현재 실행 기록 전체와 다릅니다.")
    for key, expected_hash in bound_hashes.items():
        actual_hash = validate_hash(audit_bindings.get(key), f"audit.bindings.{key}")
        if actual_hash != expected_hash:
            errors.append(f"감사 기록의 {key}가 실행 기록의 정본 결속과 다릅니다.")

    auditor = require_object(audit.get("auditor"), "auditor")
    auditor_agent = require_string(auditor.get("agent"), "auditor.agent")
    if auditor_agent == executor_agent:
        errors.append("실행자와 감사자는 서로 달라야 합니다.")
    results = require_object(audit.get("results"), "감사 results")
    if set(results) != set(cases):
        missing = sorted(set(cases) - set(results))
        extra = sorted(set(results) - set(cases))
        errors.append(f"감사 기록 사례 ID 불일치: 누락={missing}, 초과={extra}")

    checked_results = {}
    for case_id in sorted(set(cases) & set(results) & set(outputs)):
        result = require_object(results[case_id], f"감사 {case_id}")
        if result.get("criteriaId") != cases[case_id]["criteriaId"]:
            errors.append(f"{case_id}: 감사 criteriaId가 사례 정본과 다릅니다.")
        if result.get("criteriaId") not in criteria:
            errors.append(f"{case_id}: 감사 criteriaId가 평가 규약 표에 없습니다.")
        output_hash = validate_hash(result.get("outputSha256"),
                                    f"감사 {case_id}.outputSha256")
        if output_hash != sha256_text(outputs[case_id]):
            errors.append(f"{case_id}: outputSha256가 실행 출력과 다릅니다.")
        dimensions = require_object(result.get("dimensions"), f"감사 {case_id}.dimensions")
        if set(dimensions) != REQUIRED_DIMENSIONS:
            missing = sorted(REQUIRED_DIMENSIONS - set(dimensions))
            extra = sorted(set(dimensions) - REQUIRED_DIMENSIONS)
            errors.append(
                f"{case_id}: 감사 dimensions 이름 불일치: 누락={missing}, 초과={extra}"
            )
        for dimension, value in dimensions.items():
            if not isinstance(dimension, str) or not dimension:
                errors.append(f"{case_id}: 감사 dimension 이름이 올바르지 않습니다.")
            if value not in ALLOWED_RESULTS:
                errors.append(f"{case_id}/{dimension}: 알 수 없는 판정값 {value!r}")
        result_value = result.get("result")
        if result_value not in ALLOWED_RESULTS:
            errors.append(f"{case_id}: 알 수 없는 종합 판정값 {result_value!r}")
        elif all(value in ALLOWED_RESULTS for value in dimensions.values()):
            expected = expected_result(dimensions)
            if result_value != expected:
                errors.append(
                    f"{case_id}: dimensions에서 계산한 판정 {expected!r}와 result {result_value!r}가 다릅니다."
                )
        require_string(result.get("reason"), f"감사 {case_id}.reason")
        checked_results[case_id] = result
        count += 1

    overall = audit.get("overall")
    if overall not in ALLOWED_RESULTS:
        errors.append(f"감사 overall 판정값이 올바르지 않습니다: {overall!r}")
    elif len(checked_results) == len(cases):
        expected = expected_overall(checked_results)
        if overall != expected:
            errors.append(
                f"사례 판정에서 계산한 overall {expected!r}와 기록된 {overall!r}가 다릅니다."
            )
    limitations = audit.get("limitations")
    if not ((isinstance(limitations, str) and limitations.strip()) or
            (isinstance(limitations, list) and limitations and
             all(isinstance(item, str) and item.strip() for item in limitations))):
        errors.append("감사 limitations에는 비어 있지 않은 한계 설명이 있어야 합니다.")

    return count, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "evidence", nargs="?", type=Path,
        help=("명시하면 과거 schemaVersion 1/2 기록 내부의 보호 구간만 검사하며 현재 Skill·독립 "
              "감사 결속은 검증하지 않는다. 생략하면 현재 v3 실행·v2 감사를 검사한다."),
    )
    args = parser.parse_args()
    evidence_path = args.evidence or ROOT / CURRENT_PATHS["evidence"]
    try:
        evidence = require_object(json.loads(read_text(evidence_path)), "행동 기록")
        schema_version = evidence.get("schemaVersion")
        if args.evidence is None:
            if schema_version != 3:
                raise ValueError("기본 행동 기록은 schemaVersion 3이어야 합니다.")
            count, errors = check_current(evidence_path)
        elif schema_version == 3:
            count, errors = check_current(evidence_path)
        elif schema_version == 2:
            count, errors = check_schema2(evidence)
        elif schema_version in (None, 1):
            snapshot = normalized(evidence["skill"])
            if sha256_text(snapshot).lower() != evidence["skillSha256"].lower():
                raise ValueError("기록된 지침 스냅샷과 해시가 일치하지 않습니다.")
            holdout = read_text(ROOT / "tests/HOLDOUT_CASES.md")
            count, errors = check_legacy(evidence, holdout)
        else:
            raise ValueError(f"지원하지 않는 schemaVersion입니다: {schema_version!r}")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    if errors:
        raise SystemExit("\n".join(errors))
    if args.evidence is not None and schema_version != 3:
        print(
            f"과거 기록 내부 보호 구간 {count}개 통과. 현재 Skill·사례 정본·평가 규약·"
            "독립 감사와의 결속은 이 형식으로 검증할 수 없습니다."
        )
    else:
        print(
            f"정본·보호 문자열·독립 감사 결속 {count}개 통과. "
            "의미·격식·자연스러움은 자동 채점하지 않습니다."
        )


if __name__ == "__main__":
    main()
