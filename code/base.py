import re
import logging
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
from packages.core.models import AuctionItem, ItemStatus

# 로깅 설정
logger = logging.getLogger("crawler")

class BaseParser:
    """모든 파서의 기본 클래스"""
    def __init__(self, session):
        self.session = session

    def normalize_text(self, text: str) -> str:
        """텍스트 정규화 (공백 제거 및 클리닝)"""
        if not text: return ""
        return re.sub(r'\s+', ' ', text).strip()

    def extract_table_data(self, soup: BeautifulSoup) -> Dict[str, str]:
        """
        HTML 내 모든 테이블의 Key-Value 쌍을 추출합니다.
        단순 행 단위 파싱뿐만 아니라 레이블 행/값 행 분리 구조도 대응합니다.
        """
        table_data = {}
        for table in soup.find_all('table'):
            all_rows = table.find_all('tr')
            for idx, tr in enumerate(all_rows):
                ths = tr.find_all('th')
                tds = tr.find_all('td')
                
                # 1. 한 행 내에 th와 td가 섞인 경우 (th1, td1, th2, td2...)
                if ths and tds:
                    # th 바로 뒤의 td를 매칭
                    for th in ths:
                        label = re.sub(r'\s+', '', th.get_text(strip=True))
                        if not label: continue
                        val_td = th.find_next_sibling('td')
                        if val_td:
                            table_data[label] = self.normalize_text(val_td.get_text())
                
                # 2. 이번 행이 모두 th이고, 다음 행이 모두 td인 경우 (KAPT 단지정보 등)
                elif ths and not tds and idx + 1 < len(all_rows):
                    next_tr = all_rows[idx + 1]
                    next_tds = next_tr.find_all('td')
                    if len(ths) == len(next_tds):
                        for th, td in zip(ths, next_tds):
                            label = re.sub(r'\s+', '', th.get_text(strip=True))
                            if label:
                                table_data[label] = self.normalize_text(td.get_text())
                                
                # 3. 짝수 셀 (Old logic fallback)
                elif len(tr.find_all(['td', 'th'])) % 2 == 0:
                    cells = tr.find_all(['td', 'th'])
                    norm_keys = [re.sub(r'\s+', '', c.get_text(strip=True)) for c in cells]
                    raw_vals = [self.normalize_text(c.get_text()) for c in cells]
                    for i in range(0, len(cells), 2):
                        if norm_keys[i] and i+1 < len(raw_vals):
                            if norm_keys[i] not in table_data: # 기존 값 우선
                                table_data[norm_keys[i]] = raw_vals[i+1]
        return table_data

    def get_value_by_keys(self, data: Dict[str, str], keys: List[str]) -> str:
        """여러 후보 키 중 존재하는 첫 번째 값을 반환합니다."""
        for k in keys:
            norm_k = re.sub(r'\s+', '', k)
            if norm_k in data:
                return data[norm_k]
        return ""

    def update_status_by_text(self, item: AuctionItem, status_text: str):
        """텍스트 기반으로 ItemStatus를 업데이트합니다."""
        if not status_text: return
        
        if "낙찰" in status_text: item.status = ItemStatus.WON
        elif "취소" in status_text: item.status = ItemStatus.CANCELLED
        elif "유찰" in status_text: item.status = ItemStatus.NO_BIDDER
        elif "재공고" in status_text: item.status = ItemStatus.NEW # 재공고도 신규 취급
