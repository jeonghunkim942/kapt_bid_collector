import re
import time
import random
import requests
import logging
import urllib.parse
from bs4 import BeautifulSoup
from typing import List
from datetime import datetime
from packages.core.models import AuctionItem

# 로거 설정
logger = logging.getLogger("crawler")

class KaptScraper:
    """K-APT 목록 수집기"""
    BASE_URL = "https://www.k-apt.go.kr"
    LIST_URL = f"{BASE_URL}/bid/bidList.do"
    
    UA_LIST = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(self.UA_LIST),
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.k-apt.go.kr/'
        })

    def scrape_list(self, start_date: str, end_date: str, keyword: str = "승강기", search_date_gb: str = "reg", bid_type: str = "", bid_state: str = "") -> List[AuctionItem]:
        """
        KAPT 목록 조회
        :param search_date_gb: reg(공고일), bid(입찰마감일)
        :param bid_type: 빈 문자열(전체), 4(물품), 3(용역), 2(공사)
        :param bid_state: 빈 문자열(전체), 5(낙찰공고) 등
        """
        items = []
        s_str = start_date.replace('-', '')
        e_str = end_date.replace('-', '')
        
        for p in range(1, 11):
            url = f"{self.LIST_URL}?searchBidGb=bid_gb_1&bidTitle={urllib.parse.quote(keyword)}&searchDateGb={search_date_gb}&dateStart={s_str}&dateEnd={e_str}&dateArea=1&pageNo={p}"
            if bid_type:
                url += f"&type={bid_type}"
            if bid_state:
                url += f"&bidState={bid_state}"
            
            time.sleep(random.uniform(3.0, 5.0))
            headers = {'User-Agent': random.choice(self.UA_LIST)}
            
            try:
                logger.info(f"Scraping list page {p}: {url}")
                response = self.session.get(url, headers=headers, timeout=15, verify=False)
                response.raise_for_status()
                
                if len(response.text) < 5000:
                    logger.warning(f"Small response ({len(response.text)}). Blocked?")
                
                soup = BeautifulSoup(response.text, 'html.parser')
                tbody = soup.find('tbody')
                
                if not tbody or "존재 하지 않습니다" in tbody.get_text() or not tbody.find_all('tr'):
                    logger.info(f"No more items at page {p}")
                    break
                    
                for row in tbody.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) < 5: continue
                    
                    # 제목 및 bid_num 추출
                    td_title = row.find('td', {'colname': 'bidTitle'})
                    if not td_title: continue
                    
                    title = td_title.get_text(strip=True)
                    onclick = td_title.get('onclick', '')
                    m = re.search(r"goView\('(\w+)'\)", onclick)
                    if not m: continue
                    
                    bid_num = m.group(1).strip()
                    if bid_num.startswith('kg2b_'):
                        detail_url = f"https://www.kg2b.com/user/bid_list/KaptBidView.action?bidcode={bid_num.replace('kg2b_', '')}"
                    else:
                        detail_url = f"{self.BASE_URL}/bid/bidDetail.do?bidNum={bid_num}"
                    
                    # 필드 맵 (colname 사용)
                    data = {td.get('colname', f'idx_{i}'): td.get_text(strip=True) for i, td in enumerate(cols)}
                    
                    # 날짜 파싱: colname 기반 우선, 없으면 인덱스 기반
                    # 전체 카테고리 검색 시 colname이 없는 경우가 있음
                    # 인덱스 구조: [0]번호 [1]종류 [2]낙찰방법 [3]제목 [4]입찰마감일 [5]상태 [6]단지명 [7]등록일
                    def extract_date(text, fallback=""):
                        """날짜 문자열에서 YYYY-MM-DD 추출"""
                        dm = re.search(r'(\d{4}-\d{2}-\d{2})', text)
                        return dm.group(1) if dm else fallback
                    
                    # 입찰마감일
                    if 'bidLimit' in data:
                        close_date = extract_date(data['bidLimit'], end_date)
                    elif len(cols) > 4:
                        close_date = extract_date(cols[4].get_text(strip=True), end_date)
                    else:
                        close_date = end_date
                    
                    # 공고일
                    if 'regDate' in data:
                        announce_date = extract_date(data['regDate'], start_date)
                    elif len(cols) > 7:
                        announce_date = extract_date(cols[7].get_text(strip=True), start_date)
                    else:
                        announce_date = start_date
                    
                    # 상태
                    status_text = data.get('status', '') or data.get('idx_5', '')
                    if not status_text and len(cols) > 5:
                        status_text = cols[5].get_text(strip=True)
                    
                    # 단지명
                    apt_name = data.get('kaptName', '') or data.get('apt_name', '')
                    
                    item = AuctionItem(
                        bid_num=bid_num,
                        title=title,
                        url=detail_url,
                        announce_date=announce_date,
                        close_date=close_date,
                        search_keywords=[keyword],
                        category=data.get('idx_1', ''), # 종류
                        awarding_method=data.get('idx_2', ''), # 낙찰방법
                        status_text=status_text,
                        apt_name=apt_name
                    )
                    items.append(item)
                    
            except Exception as e:
                logger.error(f"Error scraping list page {p}: {e}")
                
        return items
