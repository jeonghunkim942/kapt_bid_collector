# KAPT 낙찰정보 가져오기 — 개발 다이어리

---

## 2026-03-11 (화) — KG2B 낙찰결과 수집 재활성화 및 단계적 폴백 설계

### 📌 배경

3월 7일 대응으로 KG2B 물건 수집을 완전히 비활성화한 이후, 며칠간 배치를 돌린 결과 KAPT 물건만 낙찰결과가 저장되고 KG2B 물건은 목록만 미수집 시트에 쌓이는 상태가 지속됨.

GitHub Actions(해외 IP) 환경에서는 KG2B WAF 차단이 여전하지만, **연결이 성공하는 경우도 존재**할 수 있으므로 "무조건 스킵" 대신 "일단 시도하고, 반복 실패 시 폴백" 전략으로 전환.

### ✅ 변경 내용 (`main.py`)

| 항목 | 이전 | 이후 |
|------|------|------|
| KG2B 수집 여부 | 무조건 스킵, 미수집 시트만 기록 | 낙찰결과 수집 시도 후 실패 시 미수집 시트로 폴백 |
| KG2B 세션 | 사용 안 함 | `create_kg2b_session()` 으로 별도 세션 생성 |
| 실패 처리 | - | 연속 3회 실패 시 `kg2b_blocked=True` 전환 |

**새 로직 흐름:**

```
KG2B 물건 발견
    ├─ kg2b_blocked == True  →  미수집 시트 바로 적재
    └─ kg2b_blocked == False →  get_kg2b_bidders() 호출 (내부 3회 재시도 포함)
            ├─ 성공  →  연속 실패 카운터 초기화, 메인 시트(total_new_rows)에 저장
            └─ 실패 (need_new_session=True)
                    ├─ 연속 실패 횟수 += 1, 이 물건 → 미수집 시트 적재
                    ├─ 실패 < 3회  →  세션 재생성 후 다음 물건 계속 시도
                    └─ 실패 >= 3회 →  kg2b_blocked = True, 이후 전체 KG2B 미수집 처리
```

### 📚 Lessons Learned

#### 1. "전체 차단"보다 "단계적 폴백"이 더 안전한 설계
- WAF 차단은 항상 100% 일관되지 않을 수 있음 (IP 로테이션, 시간대별 정책 차이 등)
- 무조건 스킵보다는 **일단 시도 → 반복 실패 시 폴백** 패턴이 데이터 유실을 최소화함

#### 2. "연속 실패" 기준이 중요
- `get_kg2b_bidders()`는 내부에서 이미 3회 재시도 후 실패를 반환함
- 외부 루프에서 추가로 3회 연속 실패를 카운트 → 총 최대 9번 시도 후 차단 전환
- 성공 시 카운터를 초기화하므로, 간헐적 실패(일시적 네트워크 문제)에도 차단 전환되지 않음

---

## 2026-03-07 (금) — KG2B 봇 차단 대응

### 📌 문제 상황

GitHub Actions에서 KG2B(학교장터) 상세페이지에 접속할 때 `ConnectTimeoutError`가 반복 발생하여 전체 데이터 수집이 중단됨.

```
[치명적 오류] KG2B 상세조회 커넥션 에러 kg2b_127259:
  HTTPSConnectionPool(host='www.kg2b.com', port=443): Max retries exceeded
  (Caused by ConnectTimeoutError)
```

### 🔍 원인 분석 과정

1. **첫 번째 가설: TLS fingerprint 차단**
   - `requests` 라이브러리의 고정된 TLS fingerprint(JA3)가 봇으로 탐지된다고 판단
   - `curl_cffi`를 도입하여 Chrome 브라우저의 TLS fingerprint를 모방
   - **로컬 테스트: 성공** (bidcode=127259 상세페이지 정상 접근, HTTP 200)
   - **GitHub Actions: 여전히 실패** → TLS fingerprint만으로는 해결 안 됨

2. **두 번째 가설: GitHub Actions IP 차단**
   - GitHub Actions 워크플로우에 네트워크 진단 스텝을 추가하여 테스트
   - 결과:
     ```
     내 IP: 13.83.217.50 (Azure 미국 데이터센터)
     KAPT: HTTP 200, 0.74초 → 정상
     KG2B: HTTP 000, 0.43초 → 연결 거부 (빈 응답)
     포트 443: 연결 성공 → TCP는 열림
     ```
   - **결론: IP 방화벽이 아니라, WAF(웹 방화벽)가 해외/클라우드 IP를 TLS 핸드셰이크 단계에서 차단**

### ✅ 최종 적용 사항

| 변경 파일 | 내용 |
|-----------|------|
| `main.py` | KAPT 물건만 상세조회, KG2B 물건은 스킵 후 별도 시트에 저장 |
| `sheets_handler.py` | 'KG2B 미수집' 시트탭 자동 생성 + 저장 함수 추가 |
| `kg2b_parser.py` | UA 로테이션, 지수 분포 딜레이, Referer 체인 개선 (로컬 실행용) |
| `scraper.yml` | `curl_cffi` 의존성 추가 |

**동작 흐름:**
- GitHub Actions: KAPT만 수집 → KG2B는 `입찰마감일/물건번호/입찰제목/상세페이지URL`을 'KG2B 미수집' 시트에 기록
- 로컬 PC: 'KG2B 미수집' 시트의 물건들을 별도로 수집 가능

### 📚 Lessons Learned

#### 1. Connection Timeout vs Read Timeout 구분이 핵심
- **Connection Timeout** = TCP 연결 자체가 안 됨 → IP/네트워크 레벨 차단
- **Read Timeout** = 연결은 됐지만 응답이 없음 → 서버 과부하 또는 rate limit
- 처음에 TLS fingerprint 문제로 판단했지만, Connection Timeout이라는 점에서 네트워크 레벨 차단을 더 먼저 의심했어야 함

#### 2. GitHub Actions는 Azure 미국 IP를 사용한다
- `ubuntu-latest` = Azure 미국 데이터센터 (IP: `13.83.x.x` 등)
- 한국 공공/교육기관 웹사이트(KG2B 등)는 **해외 IP를 WAF로 차단**하는 경우가 많음
- K-APT는 해외 IP를 허용하지만, KG2B는 차단함 → 동일 스크래퍼라도 사이트별로 동작이 다를 수 있음

#### 3. HTTP 000 응답 = TLS 핸드셰이크 단계 차단
- TCP 포트는 열려있는데(443 연결 성공) HTTP 응답이 000(빈 응답)이고 매우 빠르게(0.43초) 끊기는 경우
- → 서버 또는 WAF가 **TLS 핸드셰이크 과정에서 클라이언트 IP를 검사**하고 연결을 즉시 끊는 것
- IP 방화벽(포트 차단)과는 다른 레이어의 차단 방식

#### 4. 네트워크 진단은 GitHub Actions에서 직접 해야 한다
- 로컬과 GitHub Actions의 네트워크 환경이 완전히 다름
- 워크플로우에 `curl` 기반 진단 스텝을 추가하면 빠르게 원인을 파악할 수 있음
- `curl -s -o /dev/null -w "HTTP %{http_code}, %{time_total}s"` 패턴이 유용함

#### 5. `curl_cffi`는 TLS fingerprint 우회에 효과적이지만 만능은 아님
- **효과적인 경우**: 서버가 TLS fingerprint(JA3)만으로 봇을 판별할 때
- **효과 없는 경우**: IP 대역 자체를 차단하는 WAF (KG2B의 경우)
- 로컬에서는 `curl_cffi`로 해결되었으므로, IP 차단이 아닌 환경(한국 IP)에서는 유효한 전략

#### 6. 크롤링 설계 시 "수집 불가 물건"에 대한 전략을 미리 세워야 함
- 특정 사이트만 접근 불가할 때 전체 프로세스를 중단하면 다른 사이트의 데이터도 수집 못함
- **별도 시트에 미수집 물건을 기록**하는 패턴이 유용함 (나중에 로컬이나 다른 환경에서 재수집 가능)
