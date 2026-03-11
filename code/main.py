import os
import re
import time
import random
import math
import urllib.parse
import requests
import urllib3
from bs4 import BeautifulSoup
import pandas as pd
import datetime

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    print("[알림] curl_cffi 미설치. KG2B 봇 차단 우회 기능이 제한됩니다. pip install curl_cffi")

from sheets_handler import get_google_sheet, append_to_sheet, append_kg2b_pending

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────
CSV_FILE = os.path.join(os.path.dirname(__file__), "bidders_result.csv")
# 9월 2일부터 시작하도록 지정
CRAWL_START_DATE = "2024-09-02" 

BASE_URL = "https://www.k-apt.go.kr"
LIST_URL = f"{BASE_URL}/bid/bidList.do"

UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
]

# curl_cffi impersonate 옵션 목록 (Chrome 브라우저 TLS fingerprint 모방)
CFI_IMPERSONATE_LIST = ["chrome120", "chrome116", "chrome110", "chrome107", "chrome104"]

COLUMNS = [
    '입찰마감일', '물건번호', '낙찰방법', '입찰제목', '낙찰 순번',
    '응찰회사명', '응찰회사사업자번호', '대표자명', '입찰금액',
    '평가점수', '낙찰여부', '낙찰회사주소'
]


def create_session():
    """KAPT용 requests 세션 생성 및 HTTP 관련 우회 설정 강화"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://www.k-apt.go.kr/',
        'Connection': 'keep-alive',
        'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    })
    
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[ 500, 502, 503, 504 ])
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    
    try:
        session.get("https://www.k-apt.go.kr/", verify=False, timeout=10)
        time.sleep(2)
    except Exception as e:
        print(f"[초기 세션 연결 오류] {e}")
        
    return session


def create_kg2b_session():
    """
    KG2B 전용 세션 생성.
    curl_cffi를 사용하여 Chrome TLS fingerprint를 모방하고,
    KG2B 메인페이지를 먼저 방문하여 쿠키/세션을 확보합니다.
    """
    impersonate = random.choice(CFI_IMPERSONATE_LIST)
    ua = random.choice(UA_LIST)
    
    if HAS_CURL_CFFI:
        session = cffi_requests.Session(impersonate=impersonate)
        session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
    else:
        # curl_cffi 미설치 시 fallback (일반 requests)
        session = requests.Session()
        session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })

    # KG2B 메인페이지 방문하여 쿠키/세션 확보 (브라우저와 동일한 흐름)
    try:
        print(f"   [KG2B] 세션 초기화 (impersonate={impersonate})")
        session.get("https://www.kg2b.com/", timeout=15, verify=False)
        time.sleep(random.uniform(1.0, 3.0))
    except Exception as e:
        print(f"   [KG2B] 메인페이지 접속 실패 (세션은 생성됨): {e}")
    
    return session


def _jittered_delay(base_min=2.0, base_max=5.0):
    """
    지수 분포 기반 불규칙 딜레이. 평균은 base_min~base_max 사이지만
    가끔 짧고 가끔 긴 자연스러운 패턴을 생성합니다.
    sleep 시간의 상한을 base_max * 1.5로 제한합니다.
    """
    mean = (base_min + base_max) / 2.0
    delay = random.expovariate(1.0 / mean)
    delay = max(base_min, min(delay, base_max * 1.5))
    time.sleep(delay)


def scrape_awarded_list(session, date_str):
    """
    특정 날짜의 낙찰공고 목록 조회.
    type=3: 사업자 선정(경쟁입찰) 결과 공개 페이지
    bidState=5: 낙찰공고
    searchDateGb=bid: 입찰마감일 기준
    
    Returns: list of dict (bid_num, title, close_date)
    """
    items = []
    d_str = date_str.replace('-', '')
    
    for page in range(1, 100):  # 충분한 페이지 수
        url = (
            f"{LIST_URL}?searchBidGb=bid_gb_1"
            f"&bidTitle="
            f"&searchDateGb=bid"
            f"&dateStart={d_str}&dateEnd={d_str}"
            f"&dateArea=1"
            f"&pageNo={page}"
            f"&type=3"
            f"&bidState=5"
        )
        
        time.sleep(random.uniform(3.0, 5.0))
        # 헤더를 세션에 이미 설정했지만 추가로 Accept를 명시
        headers = {
            'User-Agent': random.choice(UA_LIST),
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        try:
            response = session.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            
            # 302 리다이렉트(로그인 페이지)면 중단
            if '/login/' in response.url:
                print(f"      [!] 세션 만료/차단 감지 (page {page}). 잠시 대기 후 재시도...")
                time.sleep(10)
                break
            
            soup = BeautifulSoup(response.text, 'html.parser')
            tbody = soup.find('tbody')
            
            if not tbody or not tbody.find_all('tr'):
                break
            
            rows = tbody.find_all('tr')
            page_items = 0
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5:
                    continue
                
                # bidTitle colname이 있는 td에서 제목 및 bid_num 추출
                td_title = row.find('td', {'colname': 'bidTitle'})
                if not td_title:
                    # colname이 없으면 onclick이 있는 td에서 goView 추출
                    for td in cols:
                        onclick = td.get('onclick', '')
                        if 'goView' in onclick:
                            td_title = td
                            break
                
                if not td_title:
                    continue
                
                onclick = td_title.get('onclick', '')
                m = re.search(r"goView\('(\w+)'\)", onclick)
                if not m:
                    continue
                
                bid_num = m.group(1).strip()
                
                # 제목: bidTitle colname인 td에서 가져오기
                title_td = row.find('td', {'colname': 'bidTitle'})
                title = title_td.get_text(strip=True) if title_td else cols[3].get_text(strip=True)
                # 제목 정리 (줄바꿈, 탭 제거)
                title = re.sub(r'\s+', ' ', title).strip()
                
                # 낙찰방법은 주로 5번째 또는 6번째 컬럼에 위치 ('적격심사제', '최저낙찰제' 등)
                bid_method = ""
                # KAPT 결과공개 페이지에서는 '낙찰방법'이 td 배열의 특정 인덱스에 있거나 class="bid" 형태의 span으로 존재
                bid_span = row.find('span', class_=re.compile(r'^bid'))
                if bid_span:
                    bid_method = bid_span.get_text(strip=True)
                elif len(cols) > 5:
                    bid_method = cols[5].get_text(strip=True)
                
                items.append({
                    'bid_num': bid_num,
                    'title': title,
                    'close_date': date_str,
                    'bid_method': bid_method,
                })
                page_items += 1
            
            if page_items == 0:
                break
                
        except Exception as e:
            print(f"      [오류] 목록 조회 page {page}: {e}")
            break
    
    return items


def get_bidders(session, bid_num):
    """
    개별 입찰번호의 상세 페이지에서 응찰회사 테이블 파싱. (K-APT 전용)
    낙찰자(Y) 행 바로 다음 <tr>에 '회사주소 : ...' 형태로 주소가 표시됨.
    """
    url = f"https://www.k-apt.go.kr/bid/bidDetail.do?bidNum={bid_num}"
    try:
        time.sleep(random.uniform(2.0, 5.0))
        response = session.get(url, timeout=15, verify=False)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        bid_method_detail = ""
        # 1) 기본정보 테이블에서 낙찰방법/낙찰자결정방법 추출
        for table in soup.find_all('table'):
            ths = [th.get_text(strip=True).replace(' ', '') for th in table.find_all('th')]
            for target_th in ['낙찰방법', '낙찰자결정방법']:
                if target_th in ths:
                    idx = ths.index(target_th)
                    tds = table.find_all('td')
                    if idx < len(tds):
                        bid_method_detail = tds[idx].get_text(strip=True)
                    break
            if bid_method_detail:
                break

        bidders = []
        for table in soup.find_all('table'):
            header_tr = None
            ths = []
            # '낙찰여부'가 포함된 정확한 헤더 행(tr) 찾기
            for tr in table.find_all('tr'):
                th_texts = [th.get_text(strip=True).replace('\\n', '').replace('\\r', '').replace(' ', '') for th in tr.find_all('th')]
                if '낙찰여부' in th_texts:
                    header_tr = tr
                    ths = th_texts
                    break

            if not header_tr:
                continue

            # 동적 인덱스 추출 (정확한 헤더 행 기준이므로 밀림 방지)
            idx_rank = ths.index('순번') if '순번' in ths else 0
            idx_company = ths.index('응찰회사') if '응찰회사' in ths else 1
            idx_biznum = ths.index('사업자등록번호') if '사업자등록번호' in ths else 2
            idx_ceo = ths.index('대표자') if '대표자' in ths else 3
            idx_amount = ths.index('응찰금액') if '응찰금액' in ths else 8
            idx_score = ths.index('평가점수') if '평가점수' in ths else -1
            idx_won = ths.index('낙찰여부')

            all_rows = table.find_all('tr')
            for row_idx, row in enumerate(all_rows):
                if row == header_tr:
                    continue # 헤더 행 자체 스킵
                    
                cells = row.find_all('td')
                # 데이터 행의 td 개수는 보통 ths 개수이거나 체크박스(선택) 때문에 ths-1개일 수 있음.
                # 3칸 이하인 경우(컬럼 그룹 헤더나 주소행 등)는 데이터 행 아님
                if not cells or len(cells) < len(ths) - 2:
                    continue
                # colspan을 가진 단일 행은 보통 주소행
                if len(cells) == 1 and cells[0].has_attr('colspan'):
                    continue

                # '선택' 체크박스가 헤더에는 있지만 td에는 없는 구조를 대비한 offset
                offset = len(ths) - len(cells) if len(ths) > len(cells) else 0
                
                def get_cell_text(idx):
                    adjusted_idx = idx - offset if idx > 0 else idx
                    return cells[adjusted_idx].get_text(strip=True) if 0 <= adjusted_idx < len(cells) else ""

                rank = get_cell_text(idx_rank)
                company = get_cell_text(idx_company)
                biz_num = get_cell_text(idx_biznum)
                ceo_name = get_cell_text(idx_ceo)
                amount = get_cell_text(idx_amount).replace(',', '').replace('*', '')  # 블라인드(*) 제거
                score = get_cell_text(idx_score) if idx_score != -1 else ""
                is_won = get_cell_text(idx_won)

                # 낙찰회사주소: 낙찰자(Y/YN 형태) 행 바로 다음 <tr>에서 추출
                address = ""
                if 'Y' in is_won.upper() and row_idx + 1 < len(all_rows):
                    next_row = all_rows[row_idx + 1]
                    next_td = next_row.find('td', colspan=True)
                    if next_td:
                        addr_text = next_td.get_text(strip=True)
                        addr_match = re.search(r'회사주소\\s*:\\s*(.+)', addr_text)
                        if addr_match:
                            address = addr_match.group(1).strip()

                bidders.append({
                    '낙찰 순번': rank,
                    '응찰회사명': company,
                    '응찰회사사업자번호': biz_num,
                    '대표자명': ceo_name,
                    '입찰금액': amount,
                    '평가점수': score,
                    '낙찰여부': is_won,
                    '낙찰회사주소': address,
                })
            
            return bid_method_detail, bidders
            
        return bid_method_detail, bidders
    except requests.exceptions.RequestException as e:
        print(f"      [치명적 오류] KAPT 상세조회 커넥션 에러 {bid_num}: {e}")
        raise e
    except Exception as e:
        print(f"      [오류] 상세조회 {bid_num}: {e}")
        return "", []


def get_kg2b_bidders(kg2b_session, bid_num):
    """
    KG2B (학교장터) 개별 입찰번호의 상세 페이지에서 응찰회사 정보 파싱.
    bid_num 형태: 'kg2b_123456'
    kg2b_session: create_kg2b_session()으로 생성된 KG2B 전용 세션
    
    Returns: (bid_method, bidders, need_new_session)
      need_new_session: True이면 호출자가 세션을 재생성해야 함
    """
    bid_code = bid_num.replace('kg2b_', '')
    url = f"https://www.kg2b.com/user/bid_list/KaptBidView.action?bidcode={bid_code}"
    
    try:
        # KG2B 서버 커넥션 타임아웃 지연 시 명시적 3회 재시도
        # 재시도마다 UA를 변경하고 지수 분포 딜레이 적용
        response = None
        for attempt in range(3):
            try:
                _jittered_delay(3.0, 6.0)
                headers = {
                    'User-Agent': random.choice(UA_LIST),
                    'Referer': 'https://www.kg2b.com/user/bid_list/KaptBidList.action',
                    'Sec-Fetch-Site': 'same-origin',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                }
                response = kg2b_session.get(url, headers=headers, timeout=(15, 30), verify=False)
                response.raise_for_status()
                break
            except Exception as e:
                if attempt < 2:
                    wait_time = 10 * (attempt + 1)
                    print(f"      [재시도 {attempt+1}/3] KG2B 연결 지연: {bid_code} ... {wait_time}초 후 다시 시도합니다.")
                    time.sleep(wait_time)
                else:
                    # 3회 모두 실패 시 세션 재생성 필요 플래그와 함께 반환
                    print(f"      [실패] KG2B 상세조회 {bid_num}: {e}")
                    return "", [], True
        
        if response is None:
            return "", [], True
                    
        soup = BeautifulSoup(response.text, 'html.parser')
        
        bidders = []
        # KG2B 입찰 결과 테이블 찾기 (순위, 사업자등록번호, 업체명 등이 포함된 테이블)
        target_table = None
        for table in soup.find_all('table'):
            th_texts = [th.get_text(strip=True).replace(' ', '') for th in table.find_all('th')]
            if '순위' in th_texts and '사업자등록번호' in th_texts and '업체명' in th_texts:
                target_table = table
                break
                
        if not target_table:
            return "", bidders, False
            
        rows = target_table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            # KG2B KaptBidView 테이블 구조: 0:순위, 1:사업자등록번호, 2:업체명, 3:대표자, 4:투찰금액, 5:투찰일시, 6:비고
            if len(cells) < 7:
                continue
                
            rank = cells[0].get_text(strip=True)
            if not rank or rank == '1순위': # 헤더 행이나 의미없는 행 제외 
                # (가끔 헤더가 td로 되어있는 경우 대비)
                if '순위' in rank or '사업자' in cells[1].get_text():
                    continue
                    
            biz_num = cells[1].get_text(strip=True)
            company = cells[2].get_text(strip=True)
            ceo_name = cells[3].get_text(strip=True)
            raw_amount = cells[4].get_text(strip=True)
            amount = re.sub(r'[^0-9]', '', raw_amount)  # 숫자만 추출
            note = cells[6].get_text(strip=True)
            
            # trpoint_red 클래스가 있거나 비고란에 '낙찰'이 포함되면 Y, 아니면 N
            is_won = 'Y' if ('낙찰' in note or 'trpoint_red' in row.get('class', [])) else 'N'
            
            bidders.append({
                '낙찰 순번': rank,
                '응찰회사명': company,
                '응찰회사사업자번호': biz_num,
                '대표자명': ceo_name,
                '입찰금액': amount,
                '평가점수': "",
                '낙찰여부': is_won,
                '낙찰회사주소': "",  # KG2B 목록에는 일단 주소가 표시되지 않음
            })
            
        return "", bidders, False
    except Exception as e:
        print(f"      [오류] KG2B 상세조회 {bid_num}: {e}")
        return "", [], True

def load_existing_df():
    """기존 CSV 파일을 불러오거나 빈 DataFrame 생성"""
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, dtype={'물건번호': str, '응찰회사사업자번호': str})
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df
    return pd.DataFrame(columns=COLUMNS)


def get_resume_date(df):
    """기존 데이터에서 마지막 입찰마감일을 읽어 크롤링 재개 일자를 반환."""
    if df.empty or '입찰마감일' not in df.columns:
        return datetime.date.fromisoformat(CRAWL_START_DATE)
    try:
        last_date_str = df['입찰마감일'].dropna().max()
        return datetime.date.fromisoformat(str(last_date_str)[:10])
    except Exception:
        return datetime.date.fromisoformat(CRAWL_START_DATE)


def date_range(start_date, end_date):
    """start_date부터 end_date까지 하루씩 yield"""
    current = start_date
    while current <= end_date:
        yield current
        current += datetime.timedelta(days=1)


def run_scraper_for_bidders(start_date=None, end_date=None):
    """
    일자 단위로 KAPT 낙찰공고를 조회하고 응찰회사 정보를 수집합니다.
    
    :param start_date: 수집 시작일 (str 'YYYY-MM-DD' 또는 None). None이면 기존 CSV의 마지막 입찰마감일부터 재개.
    :param end_date: 수집 종료일 (str 'YYYY-MM-DD' 또는 None). None이면 오늘 날짜.
    """
    # 1. 구글 시트에서 기존 데이터 상태 가져오기 (GitHub Actions 등 휘발성 환경에서 매우 중요)
    worksheet = None
    existing_bid_nums = set()
    last_sheet_date = None
    
    try:
        from sheets_handler import get_google_sheet, get_existing_state
        worksheet = get_google_sheet()
        if worksheet:
            last_sheet_date, sheet_existing_nums = get_existing_state(worksheet)
            if sheet_existing_nums:
                existing_bid_nums.update(sheet_existing_nums)
    except Exception as e:
        print(f"[알림] 구글 시트 연동 상태 확인 중 오류: {e}")

    # 2. 로컬 CSV 파일 처리 (로컬 환경 백업용)
    df = load_existing_df()
    if not df.empty:
        csv_existing_nums = set(df['물건번호'].unique())
        existing_bid_nums.update(csv_existing_nums)

    # 3. 재개 날짜 산정 (시트 1순위, CSV 2순위, 설정값 3순위)
    if start_date:
        resume_date = datetime.date.fromisoformat(start_date)
    else:
        if last_sheet_date:
            # 마지막으로 적힌 날짜 '다음날'부터 시작 (중복 조회 방지)
            resume_date = datetime.date.fromisoformat(last_sheet_date) + datetime.timedelta(days=1)
        elif not df.empty and '입찰마감일' in df.columns:
            resume_date = get_resume_date(df) + datetime.timedelta(days=1)
        else:
            resume_date = datetime.date.fromisoformat(CRAWL_START_DATE)
    
    today = datetime.date.fromisoformat(end_date) if end_date else datetime.date.today()

    print(f"===============================================")
    print(f"  KAPT 낙찰 응찰회사 데이터 수집기")
    print(f"  크롤링 기간: {resume_date} ~ {today}")
    print(f"  기존 데이터: {len(df)}건 / 수집된 입찰번호: {len(existing_bid_nums)}개")
    print(f"===============================================\n")

    session = create_session()
    kg2b_session = create_kg2b_session()
    total_new_rows = []
    stop_process = False
    pending_kg2b_items = []  # 별도 시트에 저장할 KG2B 물건 (수집 실패분)
    kg2b_blocked = False          # True이면 이후 KG2B 물건은 미수집 시트에만 적재
    kg2b_consecutive_failures = 0 # 연속 실패 횟수
    KG2B_MAX_FAILURES = 3         # 이 횟수 연속 실패 시 차단 처리

    for day in date_range(resume_date, today):
        if stop_process:
            break
            
        day_str = day.strftime("%Y-%m-%d")
        print(f"\n[{day_str}] 낙찰공고 조회 중...")

        # 해당 일자의 낙찰공고 목록 조회
        items = scrape_awarded_list(session, day_str)

        if not items:
            print(f"   -> 해당 일자에 낙찰공고 없음")
            continue

        # 기존에 이미 적재된 입찰번호 제외
        new_items = [item for item in items if item['bid_num'] not in existing_bid_nums]
        if not new_items:
            print(f"   -> {len(items)}건 발견, 모두 이미 적재됨 (스킵)")
            continue

        # KG2B / KAPT 분류
        kapt_items = [item for item in new_items if not item['bid_num'].startswith('kg2b_')]
        kg2b_items = [item for item in new_items if item['bid_num'].startswith('kg2b_')]

        print(f"   -> {len(items)}건 발견 (KAPT {len(kapt_items)}건, KG2B {len(kg2b_items)}건), 신규 처리 시작")

        # ── KG2B 물건 처리 ─────────────────────────────────────────
        for item in kg2b_items:
            bid_num = item['bid_num']
            close_date = item['close_date']
            title = item['title']
            bid_code = bid_num.replace('kg2b_', '')
            link = f"https://www.kg2b.com/user/bid_list/KaptBidView.action?bidcode={bid_code}"

            if kg2b_blocked:
                # 차단 상태: 낙찰결과 조회 없이 미수집 시트로 직행
                pending_kg2b_items.append({'close_date': close_date, 'bid_num': bid_num, 'title': title, 'link': link})
                existing_bid_nums.add(bid_num)
                continue

            print(f"     [KG2B {kg2b_items.index(item)+1}/{len(kg2b_items)}] {title[:50]} ({bid_num})")
            bid_method, bidders, need_new_session = get_kg2b_bidders(kg2b_session, bid_num)

            if need_new_session:
                kg2b_consecutive_failures += 1
                print(f"       -> KG2B 연결 실패 ({kg2b_consecutive_failures}/{KG2B_MAX_FAILURES})")
                if kg2b_consecutive_failures >= KG2B_MAX_FAILURES:
                    kg2b_blocked = True
                    print(f"       -> KG2B {KG2B_MAX_FAILURES}회 연속 실패. 이후 KG2B 물건은 미수집 시트에 적재합니다.")
                else:
                    print(f"       -> KG2B 세션 재생성 후 다음 물건부터 재시도합니다.")
                    kg2b_session = create_kg2b_session()
                # 이 물건은 미수집 시트에
                pending_kg2b_items.append({'close_date': close_date, 'bid_num': bid_num, 'title': title, 'link': link})
                existing_bid_nums.add(bid_num)
                continue

            # 성공 시 연속 실패 카운터 초기화
            kg2b_consecutive_failures = 0

            if not bidders:
                print(f"       -> KG2B 응찰회사 정보 없음")
                existing_bid_nums.add(bid_num)
                continue

            for bidder in bidders:
                total_new_rows.append({
                    '입찰마감일': close_date,
                    '물건번호': bid_num,
                    '낙찰방법': bid_method,
                    '입찰제목': title,
                    '낙찰 순번': bidder['낙찰 순번'],
                    '응찰회사명': bidder['응찰회사명'],
                    '응찰회사사업자번호': bidder['응찰회사사업자번호'],
                    '대표자명': bidder['대표자명'],
                    '입찰금액': bidder['입찰금액'],
                    '평가점수': bidder['평가점수'],
                    '낙찰여부': bidder['낙찰여부'],
                    '낙찰회사주소': bidder['낙찰회사주소'],
                })
            existing_bid_nums.add(bid_num)
            print(f"       -> KG2B 응찰회사 {len(bidders)}건 수집 완료")

        if not kapt_items:
            continue

        print(f"   -> KAPT {len(kapt_items)}건 상세 조회 시작")

        for idx, item in enumerate(kapt_items, 1):
            bid_num = item['bid_num']
            close_date = item['close_date']
            title = item['title']
            bid_method = item['bid_method']

            print(f"     [{idx}/{len(kapt_items)}] {title[:50]} ({bid_num})")
            
            # 항목 간 불규칙 딜레이 (차단 방지)
            _jittered_delay(2.0, 5.0)
            
            try:
                detail_method, bidders = get_bidders(session, bid_num)
            except requests.exceptions.RequestException as e:
                print(f"   [중단] KAPT 커넥션 에러로 수집을 중단합니다. ({e})")
                stop_process = True
                break
                
            # 상세조회에서 가져온 낙찰방법이 있으면 리스트 정보보다 우선 적용
            final_bid_method = detail_method if detail_method else bid_method

            if not bidders:
                print(f"       -> 응찰회사 정보 없음")
                continue

            for bidder in bidders:
                total_new_rows.append({
                    '입찰마감일': close_date,
                    '물건번호': bid_num,
                    '낙찰방법': final_bid_method,
                    '입찰제목': title,
                    '낙찰 순번': bidder['낙찰 순번'],
                    '응찰회사명': bidder['응찰회사명'],
                    '응찰회사사업자번호': bidder['응찰회사사업자번호'],
                    '대표자명': bidder['대표자명'],
                    '입찰금액': bidder['입찰금액'],
                    '평가점수': bidder['평가점수'],
                    '낙찰여부': bidder['낙찰여부'],
                    '낙찰회사주소': bidder['낙찰회사주소'],
                })

            existing_bid_nums.add(bid_num)

        if stop_process:
            break

        # 일자별 중간 저장 (크롤링 중 중단 대비)
        if total_new_rows:
            _save_to_csv(df, total_new_rows)
            # 구글 시트 연동 체크 및 저장
            worksheet = get_google_sheet()
            if worksheet:
                append_to_sheet(worksheet, total_new_rows, COLUMNS)
                
        # 하루 일치(일 단위) 조회가 끝날 때마다 서버 과부하 방지를 위해 긴 휴식
        print(f"   [Sleep] {day_str} 일자 수집 완료. 봇 차단 방지를 위해 30초 대기합니다...")
        time.sleep(30)

    # 최종 저장
    if total_new_rows:
        _save_to_csv(df, total_new_rows)
        # 이미 위의 반복문에서 중간에 저장했으나, 만일에 대비해 처리 (중복 방지 자체 내장)
        worksheet = get_google_sheet()
        if worksheet:
            append_to_sheet(worksheet, total_new_rows, COLUMNS)
            
        print(f"\n[완료] 총 {len(total_new_rows)}건의 응찰회사 데이터가 추가되었습니다.")
        print(f"   저장 위치: {CSV_FILE}")
    else:
        print(f"\n[완료] 새롭게 추가할 응찰회사 데이터가 없습니다 (모두 기존 적재 완료).")

    # KG2B 미수집 물건을 별도 시트에 저장
    if pending_kg2b_items:
        print(f"\n[KG2B] 미수집 {len(pending_kg2b_items)}건을 별도 시트에 저장합니다...")
        append_kg2b_pending(pending_kg2b_items)

def _save_to_csv(existing_df, new_rows):
    """새 데이터를 기존 DataFrame과 합쳐서 CSV로 저장"""
    new_df = pd.DataFrame(new_rows)
    if not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined = new_df
    combined = combined.drop_duplicates(subset=['물건번호', '응찰회사명'], keep='first')
    combined.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')


if __name__ == "__main__":
    # ──────────────────────────────────────────
    # 기간 설정
    # ──────────────────────────────────────────
    # 전체 기간 수집 (24년 9월 2일 ~ 현재):
    # 한번에 많이 돌면 차단되므로 GitHub Actions에서 매일 조금씩 돌리는 것을 권장합니다.
    # run_scraper_for_bidders(start_date="2024-09-02")
    #
    # 증분 수집 (기존 데이터의 마지막 입찰마감일 이후부터 현재까지):
    # (스케줄링으로 사용할 때 기본값)
    run_scraper_for_bidders()
    # ──────────────────────────────────────────
