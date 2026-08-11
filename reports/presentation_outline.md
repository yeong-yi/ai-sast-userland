# 발표 구성안 — 9장

## 1장. 문제와 목표

- UserLand 규모: C/C++ 654개, 약 235,816줄
- 문제: 전체 코드를 AI에 한 번에 넣을 수 없고 위험 함수 검색은 오탐이 많음
- 목표: 위험한 부분부터 근거로 검토하고 불확실성을 숨기지 않는 SAST
- 발표 한 문장: **많이 찾는 도구가 아니라, 왜 위험한지를 검증하는 도구**

## 2장. 전체 아키텍처

- Scanner → Context → Triage → Security Review → Verification → Report
- 각 Agent의 입력과 출력 파일을 화살표로 설명
- 외부 LLM 미사용, 사람 검토 출처 명시
- 시각 자료: `reports/architecture.html`

## 3장. 대규모 저장소 Batch 처리

- 경로 정렬 + 물리 코드 줄 수 균형으로 3개 안정 배치
- 동일 저장소와 batch 수이면 같은 경로 구간 생성
- 전체 스캔 후보와 배치 후보의 파일·줄·함수 일치 검증

| Batch | 시작 경로 | 끝 경로 | 파일 | 예상 코드 줄 | 후보 | 시간(초) | 오류 |
|---|---|---|---|---|---|---|---|
| BATCH-001 | containers/asf/asf_reader.c | host_applications/linux/apps/raspicam/RaspiPreview.c | 209 | 78,749 | 378 | 0.756 | 0 |
| BATCH-002 | host_applications/linux/apps/raspicam/RaspiPreview.h | interface/mmal/core/mmal_logging.c | 177 | 78,395 | 101 | 0.553 | 0 |
| BATCH-003 | interface/mmal/core/mmal_pool.c | vcinclude/vcore.h | 268 | 78,672 | 104 | 0.554 | 0 |

## 4장. Agent 역할 분담과 신뢰성

- Scanner: 넓게 찾기
- Context: 필요한 문맥만 모으기
- Triage: 중복 제거·우선순위
- Review: 공격 경로와 안전장치 모두 보기
- Verification: 인용 62개 원문 확인
- Report: 낮음과 정보 부족도 별도 공개

## 5장. 토큰 절약 설계

- 후보 함수 140줄, 묶음 220줄 제한
- 호출자 2개, 피호출자 3개 코드 우선 포함
- 583개 후보 중 high 11개를 10건으로 통합
- 필요한 매크로·구조체만 추가 수집
- 제외 범위와 부족 정보를 기록해 신뢰도 손실을 가시화

## 6장. 실제 3개 Batch 결과

- 배치 후보 합 583개 = 전체 후보 583개
- 오류 0건
- 후보 분포가 다른 이유: 경로별 코드 성격과 위험 함수 사용량이 다름
- 핵심 메시지: 균등 후보 수가 아니라 균형 코드량과 누락 없는 파일 배정이 목표

## 7장. AN-010 분석 사례

- 명령행 값 → apply_override → foreach_override_target → 256바이트 배열 strcpy
- 판정: 취약 가능성 높음, 신뢰도 97
- 근거: `dtoverlay.c:1852`, `dtoverlay.c:1859` 및 두 CLI 전달 경로
- 주의: 코드상 우선 후보이며 실제 공격 성공·권한 상승은 확인하지 않음

## 8장. 차별점과 한계

- 차별점: 후보 → 문맥 → 중복 통합 → 근거 검증 → 정보 부족 → 재현 보고서
- 일반 grep과 비교 표 제시
- 한계: 정규식 호출 그래프, 10건 사람 검토, 동적 검증 부재
- 정직한 한계 공개가 오히려 신뢰성을 높인다는 메시지

## 9장. 결론과 향후 계획

- 성과: 654개 파일, 3개 배치, 583개 후보, 62개 인용 검증, 제출 검증 자동화
- 다음 1: AN-010 안전한 동적 재현과 Sanitizer 확인
- 다음 2: AN-007 libfdt 문자열 종료 규약 조사
- 다음 3: 승인된 환경에서만 역할별 LLM 응답을 JSON 스키마로 연결
- 마무리: **확정할 수 있는 것과 없는 것을 분리한 근거 중심 SAST**
