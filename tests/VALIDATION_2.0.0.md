# 2.0.0 검증 기록

검증일: 2026-09-08.

## 변경 범위

일반 질문·진행 상황·짧은 확인에는 호스트의 기본 한국어 문체만 적용하고, README·메일·보고서·안내문·여러 문단의 설명문처럼 완성형 한국어 산문을 작성하거나 편집할 때만 전체 `humanizer-ko`를 사용하도록 호출 경계를 분리했다.

Skill 원본은 `skills/humanizer-ko/SKILL.md`로 옮겼다. 루트 `.codex-plugin/plugin.json`과 Claude manifest가 같은 원본을 가리키며, ChatGPT·Codex·Claude Code용 지침 예시에는 각 호스트의 직접 호출 표기를 반영했다.

## 정적 검사

- 패키지 검증에서 이름, 2.0.0 버전, manifest 경로, 세 호스트 예시, 25개 패턴, 라이선스와 고지를 확인했다.
- 검증기 회귀 테스트 22건이 통과했다. 독립형 설치 고지 누락, 잘못된 `openai.yaml` 최상위 키와 URL 접미사 변조를 거부하는 부정 대조군을 포함한다.
- Codex `quick_validate.py`와 `plugin-creator/scripts/validate_plugin.py`가 통과했다.
- `skills@1.5.20 add . --list`가 `humanizer-ko` 한 개를 찾았다.
- Claude Code 2.1.237이 marketplace와 plugin manifest를 모두 검증했다.
- 현재 2.0.0 기록의 보호 구간 비교 21개와 기존 1.0.2 기록의 비교 19개가 통과했다.

## 독립 행동 검증

[평가 규약](EVALUATION_PROTOCOL.md)의 R01–R04 조건을 출력 전에 고정했다. 실행자에게는 지침과 원문만 전달하고 기대 답안·합격 조건·과거 결과를 제공하지 않았다. 실행은 `gpt-5.6-terra / high`, 감사는 실행 모델과 변경 이력을 받지 않은 `gpt-5.6-sol / high`가 맡았다.

첫 후보는 R01–R03을 통과했지만 R04에서 한국어 과장 표현과 함께 ‘이번 변경은 업데이트’라는 기본 명제까지 삭제했다. 이를 의미 보존 실패로 판정하고, 한영 혼합문에서도 수식만 덜고 최소 사실·분류·상태를 남기도록 지침을 보강했다. 실패 출력과 판정은 [candidate-1.json](evidence/2.0.0/candidate-1.json)에 남겼다.

최종 후보의 판정은 다음과 같다.

| 사례 | 결과 | 확인 내용 |
| --- | --- | --- |
| R01 일반 채팅 | 통과 | 전체 Skill 흔적 없이 질문에 짧게 답했다. |
| R02 새 메일 작성 | 통과 | 날짜·시각·담당자·URL과 역할을 보존하고 근거 없는 사실을 추가하지 않았다. |
| R03 기존 공지 편집 | 통과 | 군더더기를 줄이고 보고 행위·오류 수·인용·명령·URL을 보존했다. |
| R04 한영 혼합문 | 통과 | 영어·기술 문자열·수치를 유지하고 한국어 과장만 줄였으며 기본 명제를 보존했다. |

실제 출력은 [final.json](evidence/2.0.0/final.json), 독립 판정은 [audit.json](evidence/2.0.0/audit.json)에 있다. `check-behavior-artifacts.py`는 현재 Skill 해시와 보호 문자열을 재검사할 뿐, 문장 의미나 자연스러움을 자동 판정하지 않는다.

## 로컬 설치 검증

작업 폴더를 `humanizer-ko` marketplace로 추가하고 `humanizer-ko@humanizer-ko` 2.0.0을 설치했다. 설치된 Skill과 `.codex-plugin/plugin.json`의 SHA-256이 작업 폴더와 일치하는지 확인했다. 독립형 Skill도 CLI로 2.0.0을 설치했으며, 배포 단위에 루트와 같은 `LICENSE`와 `THIRD_PARTY_NOTICES.md`를 포함했다.

같은 이름으로 남아 있던 수동 설치본 1.0.2는 삭제하지 않고 사용자 Codex 홈의 `backups/humanizer-ko-standalone-1.0.2-20260908`로 옮겼다. 활성 경로에는 CLI가 관리하는 2.0.0 독립형 Skill과 플러그인만 남겼다.

## 범위와 한계

행동 검증은 독립 AI 에이전트를 이용한 소규모 관측이며 모든 입력·모델에서 같은 출력을 보장하지 않는다. ChatGPT 웹 또는 데스크톱의 실제 선택 UI와 공개 원격 marketplace 배포는 이번 로컬 검증 범위에 포함하지 않았다. AI 탐지 점수도 평가하지 않았다.
