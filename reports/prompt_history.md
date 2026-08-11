# 프롬프트 이력과 실제 결과

> 이 문서의 프롬프트는 역할별 분석 지시문입니다. 이번 실행에서는 외부 LLM API를 호출하지 않았습니다. Security Review 결과는 사람이 작성했으며 `human_provided_review`입니다.

## 단계별 기록

| 단계 | Agent | 목적 | 입력 | 프롬프트/지시문 | 기대 JSON 필드 | 실제 결과 | 결과 출처 |
|---|---|---|---|---|---|---|---|
| 1 | Scanner Agent | C/C++ 파일에서 규칙에 등록된 위험 함수 호출을 찾아 검토 후보로 기록한다. | config/rules.json, target/userland | 원본 코드를 수정하지 말고 등록된 위험 함수 호출만 탐지하라. 주석과 문자열은 가능한 한 제외하고, 결과를 취약점이 아닌 review_candidate로 표시하라. | summary, candidates | 654개 파일에서 후보 583개 | deterministic_local_result |
| 2 | Context Agent | 후보가 포함된 함수, 호출자·피호출자, 인자와 제한된 코드 문맥을 수집한다. | reports/candidates.json, target/userland | 각 후보의 포함 함수와 호출 관계를 근사 수집하라. 후보당 코드 크기를 제한하고, 제외 내용과 찾지 못한 정보를 숨기지 말라. | summary, bundles | 문맥 묶음 583개, 포함 함수 누락 7개 | deterministic_local_result |
| 3 | Triage Agent | 높은 위험도 후보를 고르고 동일 함수·동일 원인의 중복을 하나의 분석 건으로 통합한다. | reports/context_bundles.json, config/security_reviews.json | critical/high 후보를 우선하되 위험 함수 이름만으로 우선순위를 확정하지 말라. 동일 버퍼와 동일 원인에 연결된 후보는 하나로 묶고 통합 이유를 기록하라. | selection_origin, selected_cases | 원본 후보 11개를 분석 10건으로 통합 | deterministic_local_result |
| 4 | Security Review Agent | 입력 경로, 인자 출처, 크기 계산과 방어 로직을 코드 근거로 분석한다. | reports/triage_selection.json, reports/context_bundles.json, config/security_reviews.json | 후보를 취약점이라고 단정하지 마라. 인자별 출처, 외부 입력 경로, 버퍼 크기, 문자열 종료, 길이 검사, 반대 근거를 파일·줄 번호와 함께 작성하라. 정보가 없으면 정보 부족으로 남겨라. | review_origin, reviews | 10건의 사람 작성 검토를 human_provided_review로 기록; 외부 LLM 호출 없음 | human_provided_review |
| 5 | Verification Agent | 모든 인용을 원본과 대조하고 공격 경로, 방어 로직, 과장된 결론을 독립적으로 점검한다. | config/security_reviews.json, target/userland | 각 인용의 파일·줄 번호·코드를 원본과 대조하라. 입력에서 위험 함수까지 경로가 끊기면 지적하고, 기존 검사를 반영하며, 실제로 확인하지 않은 공격 성공이나 권한 상승 주장을 거부하라. | analysis_id, citation_check, overall_status, final_assessment | 원본 인용 62개 검증 | deterministic_local_result |
| 6 | Report Agent | 검증된 결과를 전체·제외·정보 부족 보고서와 실행 로그로 분리해 생성한다. | reports/analysis_results.json | 검증 결과를 바꾸지 말고 요약하라. 취약 가능성 낮음과 정보 부족을 별도 보고서로 분리하고, 검토 출처가 human_provided_review임을 표시하라. | generated_files, summary | 전체·제외·정보 부족 보고서와 실행 로그를 Markdown/HTML로 생성 | deterministic_local_result |

## 프롬프트 개선의 핵심

### 초기 형태

```text
이 코드에서 취약점을 찾아줘.
```

문제점은 근거·반대 증거·정보 부족을 요구하지 않아 위험 함수만으로 과장할 수 있다는 점입니다.

### 개선 형태

```text
후보를 취약점이라고 단정하지 마라. 인자별 출처, 외부 입력 경로, 버퍼 크기,
문자열 종료, 길이 검사, 반대 근거를 파일·줄 번호와 함께 작성하라.
정보가 없으면 정보 부족으로 남겨라.
```

개선 결과, 10건 중 8건은 안전장치로 낮음, 1건은 정보 부족, 1건만 높음으로 분리됐습니다. 이것은 자동 AI 분석 결과가 아니라 사람 검토와 결정론적 인용 검증의 결과입니다.

## 응답 보존 위치

- 기대 JSON 스키마: `config/agent_prompts.json`
- 사람 작성 응답: `config/security_reviews.json`
- 역할 전달 기록: `reports/security_review_responses.json`
- 검증 후 결과: `reports/analysis_results.json`
- 실제 실행 기록: `reports/agent_run_log.md`, `reports/agent_run_log.html`
