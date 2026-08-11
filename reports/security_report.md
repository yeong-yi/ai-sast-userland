# UserLand 보안 후보 검증 보고서

> 위험 함수 호출만으로 취약점을 확정하지 않았습니다. 모든 인용은 생성 시 실제 원본 줄과 대조했습니다.

## 요약

- 분석 건수: 10건
- 원본 후보 수: 11개
- 중복 묶음: 1개 후보가 동일 원인으로 통합됨
- 취약 가능성 높음: 1건
- 취약 가능성 낮음: 8건
- 정보 부족: 1건

## 최우선 검토 후보

- 분석 ID: **AN-010**
- 제목: 명령행 오버레이 값의 256바이트 배열 strcpy
- 판정: **취약 가능성 높음** (신뢰도 97/100)
- 우선 이유: 길이 제한 없는 명령행 값이 256바이트 정적 배열로 strcpy 된다.
- 주의: 코드 근거로 정한 검토 우선순위이며 실제 공격 성공이나 취약점 확정을 뜻하지 않습니다.

## 용어 설명

- **SAST**: 프로그램을 실행하지 않고 소스 코드를 읽어 보안 문제 후보를 찾는 검사입니다.
- **검토 후보**: 위험해 보이므로 추가 확인이 필요한 코드이며, 확정 취약점은 아닙니다.
- **취약 가능성 높음**: 입력 경로와 위험 동작의 연결 근거가 강하지만 동적 재현은 별도입니다.
- **취약 가능성 낮음**: 크기 검사나 안전한 할당처럼 반대 근거가 확인된 후보입니다.
- **정보 부족**: 현재 코드 묶음만으로 높음 또는 낮음을 책임 있게 결정할 수 없습니다.
- **신뢰도**: 최종 판정을 뒷받침하는 인용과 검증의 충분함을 0~100으로 표현한 값입니다.
- **오탐**: 검사기가 위험하다고 표시했지만 추가 검토에서 안전한 사용으로 확인된 경우입니다.

## 전체 판정

| 분석 ID | 원본 후보 | 위험 함수 | 최종 판정 | 신뢰도 | 검증 |
|---|---|---|---|---:|---|
| AN-001 | CAND-0001 | `sprintf` | 취약 가능성 낮음 | 98 | 반박됨 |
| AN-002 | CAND-0002 | `strcpy` | 취약 가능성 낮음 | 99 | 반박됨 |
| AN-003 | CAND-0003 | `sprintf` | 취약 가능성 낮음 | 99 | 반박됨 |
| AN-004 | CAND-0004, CAND-0005 | `strcpy` | 취약 가능성 낮음 | 93 | 반박됨 |
| AN-005 | CAND-0006 | `sprintf` | 취약 가능성 낮음 | 99 | 반박됨 |
| AN-006 | CAND-0007 | `strcpy` | 취약 가능성 낮음 | 100 | 반박됨 |
| AN-007 | CAND-0008 | `strcpy` | 정보 부족 | 74 | 추가 정보 필요 |
| AN-008 | CAND-0009 | `strcpy` | 취약 가능성 낮음 | 97 | 반박됨 |
| AN-009 | CAND-0010 | `sprintf` | 취약 가능성 낮음 | 99 | 반박됨 |
| AN-010 | CAND-0011 | `strcpy` | 취약 가능성 높음 | 97 | 확인됨 |

## AN-001 — 네트워크 캡처 파일명 sprintf

- 원본 후보: CAND-0001
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 98/100)
- 예상 유형: 반박된 스택 버퍼 오버플로 후보

### 핵심 근거

- 버퍼 크기는 300이며 sprintf 전에 필요한 크기를 검사한다. (`target/userland/containers/io/io_net.c:58`, `target/userland/containers/io/io_net.c:134`, `target/userland/containers/io/io_net.c:138`)

### 공격에 필요한 조건

- 공격자가 URI host 또는 port 길이를 조절하고 캡처 경로가 실행되어야 한다. (`target/userland/containers/io/io_net.c:313`, `target/userland/containers/io/io_net.c:332`)

### 반대 근거와 안전장치

- 초과 크기는 호출 전에 거절된다. (`target/userland/containers/io/io_net.c:134`)

### 추가 확인 사항

- 없음

## AN-002 — YUV4MPEG2 코덱 옵션 strcpy

- 원본 후보: CAND-0002
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 99/100)
- 예상 유형: 반박된 스택 버퍼 오버플로 후보

### 핵심 근거

- 원본과 대상은 같은 32바이트 크기이며 성공 원본은 널 종료된다. (`target/userland/containers/raw/raw_video_reader.c:43`, `target/userland/containers/raw/raw_video_reader.c:55`, `target/userland/containers/raw/raw_video_reader.c:93`, `target/userland/containers/raw/raw_video_reader.c:119`)

### 공격에 필요한 조건

- 공격자가 C 옵션을 제공해야 하지만 너무 긴 옵션은 복사 전에 거절된다. (`target/userland/containers/raw/raw_video_reader.c:104`, `target/userland/containers/raw/raw_video_reader.c:108`, `target/userland/containers/raw/raw_video_reader.c:150`)

### 반대 근거와 안전장치

- 배열을 가득 채운 옵션은 폐기되고 성공으로 반환되지 않는다. (`target/userland/containers/raw/raw_video_reader.c:104`, `target/userland/containers/raw/raw_video_reader.c:108`)

### 추가 확인 사항

- 없음

## AN-003 — RTSP MIME 문자열 sprintf

- 원본 후보: CAND-0003
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 99/100)
- 예상 유형: 반박된 힙 버퍼 오버플로 후보

### 핵심 근거

- 출력 구성요소와 종료문자에 맞춰 메모리를 할당한다. (`target/userland/containers/rtsp/rtsp_reader.c:935`, `target/userland/containers/rtsp/rtsp_reader.c:942`)

### 공격에 필요한 조건

- 공격자가 MIME 하위 타입을 조절할 수 있지만 동일 길이가 할당 계산에 반영된다. (`target/userland/containers/rtsp/rtsp_reader.c:921`, `target/userland/containers/rtsp/rtsp_reader.c:935`)

### 반대 근거와 안전장치

- 할당 실패 처리와 사용 후 해제가 확인된다. (`target/userland/containers/rtsp/rtsp_reader.c:936`, `target/userland/containers/rtsp/rtsp_reader.c:949`)

### 추가 확인 사항

- 없음

## AN-004 — Simple reader URI 조립 strcpy 두 건

- 원본 후보: CAND-0004, CAND-0005
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 93/100)
- 예상 유형: 반박된 힙 버퍼 오버플로 후보

### 핵심 근거

- 두 복사는 하나의 URI 조립이며 할당량이 두 문자열 길이 합과 종료문자를 포함한다. (`target/userland/containers/simple/simple_reader.c:511`, `target/userland/containers/simple/simple_reader.c:512`, `target/userland/containers/simple/simple_reader.c:516`, `target/userland/containers/simple/simple_reader.c:522`)

### 공격에 필요한 조건

- 공격자가 매우 긴 두 URI를 만들고 길이 합 산술을 넘치게 해야 한다. (`target/userland/containers/simple/simple_reader.c:495`, `target/userland/containers/simple/simple_reader.c:511`)

### 반대 근거와 안전장치

- 정상 크기 범위에서는 두 문자열을 모두 담을 공간이 있다. (`target/userland/containers/simple/simple_reader.c:511`, `target/userland/containers/simple/simple_reader.c:512`)

### 추가 확인 사항

- 상위 계층의 URI 최대 길이

## AN-005 — RTP 바이트 덤프 sprintf

- 원본 후보: CAND-0006
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 99/100)
- 예상 유형: 반박된 스택 버퍼 오버플로 후보

### 핵심 근거

- 버퍼 산식이 고정 폭 출력과 널 종료 공간에 맞는다. (`target/userland/containers/test/rtp_decoder.c:107`, `target/userland/containers/test/rtp_decoder.c:112`, `target/userland/containers/test/rtp_decoder.c:113`)

### 공격에 필요한 조건

- 공격자가 패킷 바이트를 바꿀 수 있어도 한 바이트의 출력 폭은 늘어나지 않는다. (`target/userland/containers/test/rtp_decoder.c:112`, `target/userland/containers/test/rtp_decoder.c:222`)

### 반대 근거와 안전장치

- 행 인덱스는 한 행 끝에서 즉시 초기화된다. (`target/userland/containers/test/rtp_decoder.c:113`)

### 추가 확인 사항

- 없음

## AN-006 — 테스트 서버 기본 이름 strcpy

- 원본 후보: CAND-0007
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 100/100)
- 예상 유형: 명백한 오탐에 가까운 버퍼 오버플로 후보

### 핵심 근거

- 256바이트 배열에 10바이트 미만 고정 문자열을 복사한다. (`target/userland/containers/test/stream_server.c:37`, `target/userland/containers/test/stream_server.c:45`, `target/userland/containers/test/stream_server.c:86`)

### 공격에 필요한 조건

- 공격자가 이 strcpy의 원본을 바꿀 경로가 제시된 코드에는 없다. (`target/userland/containers/test/stream_server.c:86`)

### 반대 근거와 안전장치

- 외부 이름 조회는 별도 호출이며 대상 크기를 전달한다. (`target/userland/containers/test/stream_server.c:87`)

### 추가 확인 사항

- 없음

## AN-007 — 오버레이 심볼 경로 strcpy

- 원본 후보: CAND-0008
- 최초 판정: 정보 부족
- 독립 검증: 추가 정보 필요
- 최종 판정: **정보 부족** (신뢰도 74/100)
- 예상 유형: 잠재적 경계 밖 읽기 또는 스택 버퍼 오버플로

### 핵심 근거

- 결합 길이 검사는 있으나 원본 DTB 속성의 널 종료 전제가 확인되지 않았다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1058`, `target/userland/helpers/dtoverlay/dtoverlay.c:1106`, `target/userland/helpers/dtoverlay/dtoverlay.c:1107`, `target/userland/helpers/dtoverlay/dtoverlay.c:1113`)

### 공격에 필요한 조건

- 공격자가 비정상적으로 종료된 심볼 경로를 가진 DTB를 처리시킬 수 있어야 한다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1058`, `target/userland/helpers/dtoverlay/dtoverlay.c:1113`)

### 반대 근거와 안전장치

- 256바이트 배열 크기 전달과 결합 길이 거절이 존재한다. (`target/userland/helpers/dtoverlay/dtoverlay.h:48`, `target/userland/helpers/dtoverlay/dtoverlay.c:1094`, `target/userland/helpers/dtoverlay/dtoverlay.c:1107`)

### 추가 확인 사항

- fdt_getprop_by_offset가 반환하는 문자열 속성의 종료 규약
- 이 함수 전에 수행되는 DTB 유효성 검사

## AN-008 — 내부 심볼 이름 유연 배열 strcpy

- 원본 후보: CAND-0009
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 97/100)
- 예상 유형: 반박된 힙 버퍼 오버플로 후보

### 핵심 근거

- str[1] 공간에 strlen(name) 바이트를 추가해 name과 널을 담는다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1364`, `target/userland/helpers/dtoverlay/dtoverlay.c:1388`, `target/userland/helpers/dtoverlay/dtoverlay.c:1402`)

### 공격에 필요한 조건

- name이 널 종료되지 않으면 strlen 단계가 먼저 문제가 되지만 해당 전제 위반은 확인되지 않았다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1385`, `target/userland/helpers/dtoverlay/dtoverlay.c:1388`)

### 반대 근거와 안전장치

- 할당 실패도 처리된다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1389`)

### 추가 확인 사항

- 없음

## AN-009 — 노드 이름 sprintf

- 원본 후보: CAND-0010
- 최초 판정: 취약 가능성 낮음
- 독립 검증: 반박됨
- 최종 판정: **취약 가능성 낮음** (신뢰도 99/100)
- 예상 유형: 반박된 힙 버퍼 오버플로 후보

### 핵심 근거

- 문자열 접두는 정밀도로 제한되고 32비트 16진수에 16바이트를 예약한다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1707`, `target/userland/helpers/dtoverlay/dtoverlay.c:1708`, `target/userland/helpers/dtoverlay/dtoverlay.c:1711`)

### 공격에 필요한 조건

- 공격자가 이름과 정수를 바꿀 수 있어도 출력 폭은 할당식 범위 안이다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1703`, `target/userland/helpers/dtoverlay/dtoverlay.c:1708`, `target/userland/helpers/dtoverlay/dtoverlay.c:1711`)

### 반대 근거와 안전장치

- 할당 실패도 즉시 처리된다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1709`)

### 추가 확인 사항

- 없음

## AN-010 — 명령행 오버레이 값의 256바이트 배열 strcpy

- 원본 후보: CAND-0011
- 최초 판정: 취약 가능성 높음
- 독립 검증: 확인됨
- 최종 판정: **취약 가능성 높음** (신뢰도 97/100)
- 예상 유형: CWE-121 스택 기반 버퍼 오버플로 가능성

### 핵심 근거

- 길이 제한 없는 명령행 값이 256바이트 정적 배열로 strcpy 된다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1852`, `target/userland/helpers/dtoverlay/dtoverlay.c:1859`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:416`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:427`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:446`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:448`)
- 별도 dtmerge 명령행 경로도 같은 함수에 값을 전달한다. (`target/userland/host_applications/linux/apps/dtmerge/dtmerge.c:165`, `target/userland/host_applications/linux/apps/dtmerge/dtmerge.c:185`, `target/userland/helpers/dtoverlay/dtoverlay.c:1909`)

### 공격에 필요한 조건

- 공격자가 유효한 오버레이 매개변수에 255자를 초과하는 값을 제공하고 해당 override 처리 경로를 실행해야 한다. (`target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:416`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:427`, `target/userland/host_applications/linux/apps/dtoverlay/dtoverlay_main.c:446`, `target/userland/helpers/dtoverlay/dtoverlay.c:1833`)

### 반대 근거와 안전장치

- 빈 override 데이터는 조기에 반환되지만 값 길이 제한은 아니다. (`target/userland/helpers/dtoverlay/dtoverlay.c:1833`)

### 추가 확인 사항

- 실행 바이너리의 스택 보호 옵션
- 프로그램 실행 권한과 신뢰 경계
- 재현 테스트는 아직 수행하지 않음
