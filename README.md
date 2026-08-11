# UserLand SAST 검토 후보 수집기

## 원본 코드 준비

Raspberry Pi UserLand 원본은 이 저장소에 포함하지 않습니다. 용량과 원본 저장소 이력을 분리하면서도 동일한 분석 대상을 재현하기 위해, 프로젝트 최상위 폴더에서 아래 명령으로 내려받습니다.

```powershell
.\setup_target.ps1
```

이 명령은 공식 원본 저장소(`https://github.com/raspberrypi/userland.git`)를 `target/userland`에 복제합니다. 이후 아래 실행 명령을 순서대로 수행합니다.

## 프로그램 목적

이 프로그램은 Raspberry Pi UserLand의 C/C++ 코드를 읽고, 보안 검토가 필요한 함수 호출을 빠르게 찾아줍니다.

현재 단계에서는 발견한 코드를 **실제 취약점으로 확정하지 않습니다.** 모든 결과는 사람이 주변 코드를 더 살펴봐야 하는 `review_candidate`(검토 후보)로 기록합니다.

## 현재 구성

- `config/rules.json`: 찾을 함수, 위험도, 탐지 이유
- `config/agent_prompts.json`: 여섯 에이전트의 입력 지시문과 기대 JSON 응답 스키마
- `config/security_reviews.json`: 10개 분석 건의 1차 분석, 추가 문맥 요청, 독립 검증과 최종 판정
- `src/scanner.py`: C/C++ 파일을 재귀적으로 읽는 스캐너
- `src/batch_scanner.py`: 경로·파일·코드량 기준으로 저장소를 안정적인 3개 배치로 나눠 실제 검사
- `src/context_builder.py`: 후보의 함수·호출 관계·인자를 제한된 크기로 수집하는 문맥 수집기
- `src/analyze_candidates.py`: 인용을 실제 원본과 대조하고 최종 보고서를 만드는 분석기
- `src/agent_pipeline.py`: 여섯 역할을 순서대로 실행하고 시간과 결과를 기록하는 오케스트레이터
- `src/generate_submission_docs.py`: 아키텍처·토큰 전략·프롬프트·차별점·발표 문서 생성기
- `src/validate_submission.py`: JSON·인용·보고서·원본 보존을 확인하는 제출 검증기
- `target/userland`: 검사 대상 원본 코드(수정하지 않음)
- `reports/candidates.json`: 스캐너가 만든 검토 후보 보고서
- `reports/context_bundles.json`: 후속 분석에 전달할 코드 문맥 묶음
- `reports/batch_results.json`: 세 배치의 경로·파일·코드량·후보·시간·오류와 전체 분석 비교
- `reports/triage_selection.json`: 중복 통합과 우선 분석 대상 선정 결과
- `reports/security_review_responses.json`: 사람 제공 보안 검토를 출처와 함께 기록한 전달 파일
- `reports/analysis_results.json`: 분석·추가 문맥·독립 검증·최종 판정 전체 데이터
- `reports/security_report.md`: 사람이 읽기 쉬운 전체 보안 보고서
- `reports/rejected_candidates.md`: 반박되거나 가능성이 낮아 제외한 후보
- `reports/needs_more_context.md`: 정보가 부족한 후보와 필요한 코드
- `reports/security_report.html`: 표·색상·근거가 포함된 전체 HTML 보고서
- `reports/rejected_candidates.html`: 제외 후보 HTML 보고서
- `reports/needs_more_context.html`: 정보 부족 HTML 보고서
- `reports/agent_run_log.md`, `reports/agent_run_log.html`: 역할별 실행 시간·입력·지시문·결과 로그

## 실행 방법

Python 3가 설치된 상태에서 프로젝트의 최상위 폴더에서 실행합니다.

권장 방법은 전체 역할 기반 파이프라인을 한 번에 실행하는 것입니다.

```powershell
python src/agent_pipeline.py
```

이 명령이 아래 세 기존 프로그램을 순서대로 실행하고, Triage·Security Review·Report 단계를 추가로 수행합니다. 기존 단계를 개별 실행하는 방법도 계속 지원합니다.

```powershell
python src/scanner.py
```

후보 보고서를 만든 다음 문맥 묶음을 생성합니다.

```powershell
python src/context_builder.py
```

마지막으로 검토 데이터의 모든 파일·줄 번호를 원본과 대조하고 최종 보고서를 생성합니다.

```powershell
python src/analyze_candidates.py
```

Windows에서 `python` 명령이 동작하지 않고 Python Launcher가 설치되어 있다면 다음 명령을 사용합니다.

```powershell
py -3 src/scanner.py
py -3 src/context_builder.py
py -3 src/analyze_candidates.py
py -3 src/agent_pipeline.py
```

경로를 직접 지정할 수도 있습니다.

```powershell
python src/scanner.py --target target/userland --rules config/rules.json --output reports/candidates.json
```

외부 Python 패키지는 필요하지 않습니다.

## 과제 필수 산출물

- [전체 아키텍처 Markdown](reports/architecture.md) / [HTML](reports/architecture.html)
- [토큰 절약 전략 Markdown](reports/token_strategy.md) / [HTML](reports/token_strategy.html)
- [프롬프트 이력 Markdown](reports/prompt_history.md) / [HTML](reports/prompt_history.html)
- [기존 방식과의 차별점 Markdown](reports/differentiation_report.md) / [HTML](reports/differentiation_report.html)
- [9장 발표 구성안](reports/presentation_outline.md)
- [3개 배치 실제 실행 결과](reports/batch_results.json)
- [역할별 에이전트 실행 로그 Markdown](reports/agent_run_log.md) / [HTML](reports/agent_run_log.html)
- [최종 보안 보고서 Markdown](reports/security_report.md) / [HTML](reports/security_report.html)
- [제출 전 검증 보고서 Markdown](reports/validation_report.md) / [HTML](reports/validation_report.html)

배치 결과는 세 배치 후보의 합이 전체 스캔 후보와 같은지 파일·줄·함수 기준으로 확인합니다. 문서들은 현재 JSON 결과에서 자동 생성되므로 실행 결과와 설명이 어긋날 가능성을 줄였습니다.

## 역할 기반 멀티 에이전트 구조

여기서 에이전트는 책임과 입출력이 분리된 워크플로 단계입니다.

| 에이전트 | 역할 | 주요 결과 |
|---|---|---|
| Scanner Agent | 위험 함수 호출 후보 탐지 | `candidates.json` |
| Context Agent | 함수·호출 관계·인자·주변 코드 수집 | `context_bundles.json` |
| Triage Agent | 높은 우선순위 선정과 동일 원인 중복 통합 | `triage_selection.json` |
| Security Review Agent | 입력 경로·크기·종료·방어 로직 분석 | `security_review_responses.json` |
| Verification Agent | 파일·줄 번호·인용 코드와 과장된 결론 검증 | `analysis_results.json`, Markdown 보고서 |
| Report Agent | 전체·제외·정보 부족 HTML 및 실행 로그 생성 | HTML 보고서, `agent_run_log.*` |

각 역할의 입력 지시문과 기대 JSON 스키마는 `config/agent_prompts.json`에 있습니다. 따라서 나중에 승인된 LLM 연결이 생겨도 역할별 입출력 규격을 유지할 수 있습니다.

### AI API가 없을 때

현재 파이프라인은 외부 LLM API를 연결하거나 호출하지 않습니다.

- Scanner와 Context Agent는 기존 Python 프로그램을 실행합니다.
- Triage Agent는 사람이 선정한 검토 건과 중복 이유를 구조화합니다.
- Security Review Agent는 `config/security_reviews.json`의 사람 작성 결과를 사용합니다.
- Verification Agent는 62개 인용을 실제 원본 파일과 대조합니다.
- Report Agent는 검증 결과를 Markdown과 HTML로 변환합니다.

사람이 작성한 분석에는 항상 `review_origin: human_provided_review`와 `automated_ai_analysis: false`가 붙습니다. AI가 자동으로 분석한 것처럼 표현하지 않습니다.

## 결과 파일 설명

`reports/candidates.json`에는 다음 내용이 저장됩니다.

- 검사한 C/C++ 파일 수
- 전체 검토 후보 수
- 함수별 탐지 개수
- 위험도별 탐지 개수
- 파일 읽기 오류 수
- 각 후보의 파일 경로, 줄 번호, 함수명, 코드, 위험도, 탐지 이유

현재 실행 결과는 다음과 같습니다.

| 항목 | 결과 |
|---|---:|
| 검사한 파일 | 654개 |
| 전체 검토 후보 | 583개 |
| 높은 위험도 후보 | 37개 |
| 중간 위험도 후보 | 546개 |
| 파일 읽기 오류 | 0개 |

함수별 개수는 다음과 같습니다.

| 함수 | 개수 |
|---|---:|
| `gets` | 0 |
| `strcpy` | 23 |
| `strcat` | 4 |
| `sprintf` | 10 |
| `scanf` | 0 |
| `memcpy` | 200 |
| `malloc` | 145 |
| `free` | 201 |

## 문맥 묶음 기능

`context_builder.py`는 `reports/candidates.json`을 읽고 각 후보에 다음 정보를 붙입니다.

- 후보가 들어 있는 함수의 정의 위치와 코드
- 그 함수를 부르는 함수와 호출 위치
- 그 함수가 부르는 함수와 가능한 정의 위치
- 위험 함수 호출식과 각 인자
- 후보 앞뒤 코드
- 찾지 못한 정의나 부족한 정보
- 크기 제한 때문에 제외한 코드와 관계
- 후속 AI가 지켜야 할 분석 지침과 확인 질문

모든 결과는 `reports/context_bundles.json`에 저장됩니다. 각 묶음에는 `CAND-0001`과 같은 고유 ID가 있습니다.

현재 크기 제한은 다음과 같습니다.

| 제한 | 값 |
|---|---:|
| 후보 함수 코드 | 최대 140줄 |
| 묶음 전체 코드 | 최대 220줄 |
| 코드를 포함할 호출자 | 최대 2개 |
| 코드를 포함할 피호출 함수 | 최대 3개 |
| 방향별 호출 관계 | 최대 30개 |

현재 실행 결과는 다음과 같습니다.

| 항목 | 결과 |
|---|---:|
| 색인한 파일 | 654개 |
| 찾은 함수 정의 | 4,492개 |
| 생성한 문맥 묶음 | 583개 |
| 포함 함수를 찾지 못한 묶음 | 7개 |
| 원본 파일 읽기 오류 | 0개 |
| 문맥 수집 실행 시간 | 약 29.3초 |

상위 3개 묶음을 원문과 비교한 결과 함수 범위, 위험 함수 인자, 호출자 위치가 일치했습니다. 동일한 호출자 코드가 반복되는 문제도 제거했습니다.

## 근거 검증 보안 분석

`analyze_candidates.py`는 높은 위험도의 원본 후보 11개를 읽어 동일 원인 1개를 합친 10건을 분석합니다. 이번 단계에서는 AI API나 공격 코드를 사용하지 않았습니다. 사람이 검토한 분석 내용을 `config/security_reviews.json`에 저장하고, 생성기가 다음 사항을 기계적으로 확인합니다.

- 분석 ID와 원본 후보 ID가 중복되지 않는지
- 선택한 원본 후보가 실제로 높은 위험도인지
- 모든 파일 경로가 `target/userland` 안에 있는지
- 인용한 줄 번호가 존재하는지
- 예상한 코드가 해당 줄의 실제 원문과 일치하는지
- 최초 문맥과 추가 문맥이 구분되어 있는지
- 최종 판정과 검증 상태가 허용된 값인지
- 신뢰도 점수가 0~100 범위인지

현재 검증 결과는 다음과 같습니다.

| 항목 | 결과 |
|---|---:|
| 분석 건수 | 10건 |
| 분석에 포함된 원본 후보 | 11개 |
| 동일 원인으로 통합된 후보 | 1개 |
| 검증한 코드 인용 | 62개 |
| 취약 가능성 높음 | 1건 |
| 취약 가능성 낮음 | 8건 |
| 정보 부족 | 1건 |

가장 우선적인 후보는 `AN-010`입니다. 명령행 매개변수 값이 길이 검사 없이 256바이트 배열의 `strcpy`로 전달되는 경로가 확인됐습니다. 이것은 코드상 가능성 판정이며 실제 공격 성공이나 권한 상승을 확인한 결과는 아닙니다.

## 현재 탐지 방식의 한계

- 위험한 함수가 호출됐다는 사실만 찾으며, 실제 공격 가능성은 판단하지 않습니다.
- 함수 이름이 매크로나 복잡한 문법으로 만들어지면 놓칠 수 있습니다.
- C++ 원시 문자열(raw string) 같은 일부 특수 문법은 완벽하게 처리하지 못할 수 있습니다.
- 버퍼 크기, 입력의 출처, 메모리 해제 순서 등 함수 주변의 의미를 분석하지 않습니다.
- 현재 위험도는 함수 규칙을 기준으로 하므로 같은 함수의 모든 호출에 동일한 위험도가 붙습니다.
- 주석, 문자열, 문자 리터럴과 전처리기 지시문은 가능한 한 제외하지만 정식 C/C++ 파서와 동일하지는 않습니다.
- 함수 정의와 호출 관계는 정규식 및 괄호 위치를 이용한 근사 분석입니다. 함수 포인터, 콜백, 매크로, 조건부 컴파일과 같은 C/C++ 문법은 정확히 연결하지 못할 수 있습니다.
- 같은 이름의 함수가 여러 파일에 있으면 잘못된 정의와 연결될 수 있습니다.
- `malloc`, `free`, `strlen` 같은 외부 라이브러리 함수는 저장소 안에서 정의를 찾지 못한 것으로 표시됩니다.
- 크기가 큰 함수는 후보 주변을 우선하고 나머지 범위를 `excluded_content`에 기록합니다.
- 현재 최종 보안 판정 10건은 자동 의미 분석 결과가 아니라 사람이 원문을 검토해 작성한 근거 데이터입니다. 생성기는 인용과 구조를 검증하지만 보안 판단 자체를 대신하지 않습니다.
- 실행 바이너리의 컴파일 보호 옵션, 운영체제 권한, 실제 배포 경로와 재현 결과는 아직 확인하지 않았습니다.

## 다음 개발 단계

다음 단계에서는 `AN-010`의 입력 길이 조건을 안전한 테스트 환경에서 재현 가능한지 확인하고, `AN-007`에 부족한 libfdt 문자열 종료 규약과 DTB 유효성 검사 경로를 조사합니다. 자동 패치는 검증이 끝난 뒤 별도 단계로 남겨둡니다.

## 제출 전 확인 방법

### 1. 전체 결과 다시 만들기

프로젝트 최상위 폴더에서 다음 순서로 실행합니다.

```powershell
python src/scanner.py
python src/batch_scanner.py
python src/context_builder.py
python src/analyze_candidates.py
python src/agent_pipeline.py
python src/generate_submission_docs.py
python src/validate_submission.py
```

일반 `python` 명령 대신 Windows Python Launcher를 사용한다면 `python`을 `py -3`으로 바꿉니다.

### 2. 검증 결과 확인하기

다음 두 파일에서 모든 항목이 `통과`인지 확인합니다.

- `reports/validation_report.md`: GitHub나 텍스트 편집기에서 확인
- `reports/validation_report.html`: 웹 브라우저에서 확인

검증기는 다음 내용을 자동 확인합니다.

- 후보 수와 문맥 묶음 수가 같은지
- 분석 후보 ID가 실제 후보와 연결되는지
- 모든 파일·줄 번호·인용 코드가 UserLand 원본과 일치하는지
- 판정 집계가 JSON·Markdown·HTML에서 같은지
- 필수 보고서와 에이전트 실행 로그가 존재하는지
- 중복 후보가 반복 보고되지 않았는지
- 사람 검토 출처와 AI API 미사용이 명시됐는지
- 비전공자용 용어 설명과 최우선 후보 요약이 있는지
- `target/userland` 원본에 변경이 없는지

실패한 항목도 삭제하거나 숨기지 않고 검증 보고서에 원인과 관련 파일을 기록합니다.

### 3. 제출할 핵심 파일

- `README.md`
- `src/` 전체
- `config/` 전체
- `reports/candidates.json`
- `reports/batch_results.json`
- `reports/context_bundles.json`
- `reports/analysis_results.json`
- `reports/security_report.md`, `reports/security_report.html`
- `reports/rejected_candidates.md`, `reports/rejected_candidates.html`
- `reports/needs_more_context.md`, `reports/needs_more_context.html`
- `reports/agent_run_log.md`, `reports/agent_run_log.html`
- `reports/validation_report.md`, `reports/validation_report.html`
- `reports/architecture.md`, `reports/architecture.html`
- `reports/token_strategy.md`, `reports/token_strategy.html`
- `reports/prompt_history.md`, `reports/prompt_history.html`
- `reports/differentiation_report.md`, `reports/differentiation_report.html`
- `reports/presentation_outline.md`

### 4. 제출 전에 알아둘 한계

- 이 결과는 근거 기반 검토 결과이며 취약점 확정이나 공격 성공 증명이 아닙니다.
- 함수와 호출 관계는 정규식 기반 근사 분석입니다.
- 전체 583개 후보 중 높은 우선순위 10건을 정밀 검토했습니다.
- 동적 재현, 실제 빌드 환경, 권한 경계와 컴파일 보호 옵션은 아직 검증하지 않았습니다.
- 외부 AI API가 설정되지 않은 현재 환경에서는 임의로 API를 연결하지 않습니다. 대신 `config/agent_prompts.json`에 역할별 프롬프트·응답 JSON 구조를 저장하고, `config/security_reviews.json`의 사람 작성 결과를 `human_provided_review`로 기록합니다.
