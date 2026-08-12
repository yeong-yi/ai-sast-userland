# 제출 전 자동 검증 보고서

- 전체 결과: **통과**
- 통과: 12개
- 실패: 0개
- 실행 시간: 0.2초
- 생성 시각(UTC): `2026-08-12T15:18:17.393557+00:00`

> 실패 항목도 숨기지 않고 아래 표와 상세 내용에 기록합니다.

| ID | 검증 항목 | 결과 | 관련 파일 |
|---|---|---|---|
| V01 | 필수 JSON 파일과 문법 | **통과** | reports/candidates.json, reports/context_bundles.json, reports/analysis_results.json, reports/triage_selection.json, reports/batch_results.json, config/agent_prompts.json, config/security_reviews.json |
| V02 | 후보 수와 문맥 묶음 수 일치 | **통과** | reports/candidates.json, reports/context_bundles.json |
| V03 | 분석 후보 ID 존재와 중복 제거 | **통과** | reports/candidates.json, reports/context_bundles.json, reports/analysis_results.json |
| V04 | 인용 경로·줄 번호·코드 원문 대조 | **통과** | reports/analysis_results.json, target/userland |
| V05 | 최종 판정 집계 일치 | **통과** | reports/analysis_results.json, reports/security_report.md, reports/security_report.html |
| V06 | Markdown과 HTML 보고서 생성 | **통과** | reports |
| V07 | 에이전트 실행 로그 완전성 | **통과** | config/agent_prompts.json, reports/agent_run_log.md, reports/agent_run_log.html |
| V08 | 사람 검토 출처와 AI API 미사용 표기 | **통과** | config/security_reviews.json, reports/analysis_results.json |
| V09 | 보고서 표현과 비전공자 설명 | **통과** | reports/security_report.md, reports/security_report.html |
| V10 | UserLand 원본 무변경 | **통과** | target/userland |
| V11 | 3개 배치 실행과 전체 분석 일치 | **통과** | reports/batch_results.json, reports/candidates.json |
| V12 | 과제 필수 문서와 발표 구성 | **통과** | reports/architecture.md, reports/token_strategy.md, reports/prompt_history.md, reports/differentiation_report.md, reports/presentation_outline.md |

## V01 — 필수 JSON 파일과 문법

- 결과: **통과**
- 설명: 필수 JSON 7개를 UTF-8로 읽었습니다.
- 관련 파일: `reports/candidates.json`, `reports/context_bundles.json`, `reports/analysis_results.json`, `reports/triage_selection.json`, `reports/batch_results.json`, `config/agent_prompts.json`, `config/security_reviews.json`

## V02 — 후보 수와 문맥 묶음 수 일치

- 결과: **통과**
- 설명: 후보와 문맥 묶음이 각각 583개로 일치합니다.
- 관련 파일: `reports/candidates.json`, `reports/context_bundles.json`

## V03 — 분석 후보 ID 존재와 중복 제거

- 결과: **통과**
- 설명: 분석에 사용한 11개 원본 후보 ID가 모두 실제 후보와 일치하고 중복되지 않습니다.
- 관련 파일: `reports/candidates.json`, `reports/context_bundles.json`, `reports/analysis_results.json`

## V04 — 인용 경로·줄 번호·코드 원문 대조

- 결과: **통과**
- 설명: 인용 62개의 경로·줄 번호·코드가 UserLand 원본과 일치합니다.
- 관련 파일: `reports/analysis_results.json`, `target/userland`

## V05 — 최종 판정 집계 일치

- 결과: **통과**
- 설명: 판정 집계가 JSON·Markdown·HTML에서 일치합니다: 취약 가능성 낮음 8건, 정보 부족 1건, 취약 가능성 높음 1건
- 관련 파일: `reports/analysis_results.json`, `reports/security_report.md`, `reports/security_report.html`

## V06 — Markdown과 HTML 보고서 생성

- 결과: **통과**
- 설명: 필수 Markdown/HTML 보고서 8개가 모두 존재하며 비어 있지 않습니다.
- 관련 파일: `reports`

## V07 — 에이전트 실행 로그 완전성

- 결과: **통과**
- 설명: 여섯 역할과 프롬프트 템플릿, 시간·입력·결과·실패 필드가 두 로그에 기록됐습니다.
- 관련 파일: `config/agent_prompts.json`, `reports/agent_run_log.md`, `reports/agent_run_log.html`

## V08 — 사람 검토 출처와 AI API 미사용 표기

- 결과: **통과**
- 설명: 검토 데이터와 분석 결과가 human_provided_review이며 자동 AI 분석이 아님을 명시합니다.
- 관련 파일: `config/security_reviews.json`, `reports/analysis_results.json`

## V09 — 보고서 표현과 비전공자 설명

- 결과: **통과**
- 설명: 판정 구분, 용어 설명, 최우선 후보 요약과 비확정 안내가 있으며 과장 표현은 발견되지 않았습니다.
- 관련 파일: `reports/security_report.md`, `reports/security_report.html`

## V10 — UserLand 원본 무변경

- 결과: **통과**
- 설명: target/userland Git 작업 트리에 변경이 없습니다.
- 관련 파일: `target/userland`

## V11 — 3개 배치 실행과 전체 분석 일치

- 결과: **통과**
- 설명: 3개 배치의 파일 654개와 후보 583개가 전체 분석과 일치하며 오류가 없습니다.
- 관련 파일: `reports/batch_results.json`, `reports/candidates.json`

## V12 — 과제 필수 문서와 발표 구성

- 결과: **통과**
- 설명: 필수 문서 9개, Mermaid 구성도와 9장 발표 개요가 준비됐습니다.
- 관련 파일: `reports/architecture.md`, `reports/token_strategy.md`, `reports/prompt_history.md`, `reports/differentiation_report.md`, `reports/presentation_outline.md`
