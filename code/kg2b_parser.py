import re
import time
import random
import urllib.parse
from bs4 import BeautifulSoup
from .base import BaseParser, logger
from packages.core.models import AuctionItem, ItemStatus
from packages.core.file_extractor import FileExtractor

class Kg2bParser(BaseParser):
    """KG2B (학교장터) 전용 파서"""
    
    KG2B_DOWNLOAD_BASE = "https://www.kg2b.com/common/util/download"
    
    def parse_detail(self, item: AuctionItem) -> AuctionItem:
        """KG2B 상세 정보 및 텍스트 추출"""
        bid_code = item.bid_num.replace('kg2b_', '')
        url = f"https://www.kg2b.com/user/bid_list/KaptBidView.action?bidcode={bid_code}"
        
        try:
            # KG2B 서버 WAF 차단 방지를 위한 전용 헤더 및 재시도 로직
            headers = {
                'Referer': 'https://www.kg2b.com/',
                'Sec-Fetch-Site': 'same-origin'
            }
            for attempt in range(3):
                try:
                    time.sleep(random.uniform(3.0, 6.0))
                    response = self.session.get(url, headers=headers, timeout=(15, 30), verify=False)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt < 2:
                        wait_t = 10 * (attempt + 1)
                        logger.warning(f"KG2B parse_detail delay ({item.bid_num}), retrying in {wait_t}s ...")
                        time.sleep(wait_t)
                    else:
                        raise e
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 본문 텍스트 추출
            self._extract_text(item, soup)
            
            # 테이블 데이터 매핑
            table_data = self.extract_table_data(soup)
            item.phone = self.get_value_by_keys(table_data, ['연락처', 'TEL', '전화번호'])
            item.apt_name = self.get_value_by_keys(table_data, ['단지명', '발주처', '배주처']) or item.apt_name
            item.office_address = self.get_value_by_keys(table_data, ['주소', '소재지', '현장주소'])
            
            # 파일 다운로드 (goLoad 함수 파싱)
            self._download_kg2b_files(item, soup)
            
            if item.attached_files:
                item.status = "PARSED"
            else:
                item.status = "PARSED_KG2B"
            logger.info(f"KG2B Detail parsed: {item.bid_num} (files: {len(item.attached_files)})")
            
        except Exception as e:
            logger.error(f"KG2B parse_detail error ({item.bid_num}): {e}")
            item.status = "FAILED"
            
        return item
    
    def _download_kg2b_files(self, item: AuctionItem, soup: BeautifulSoup):
        """KG2B 페이지의 goLoad() JavaScript 호출을 파싱하여 파일 다운로드"""
        try:
            # goLoad('경로/','UUID파일명','type','원본파일명') 패턴 찾기
            goload_pattern = re.compile(r"goLoad\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)")
            
            # 모든 a 태그에서 href 또는 onclick 내의 goLoad 호출 검색
            all_links = soup.find_all('a')
            texts = []
            
            for link in all_links:
                href = link.get('href', '') or ''
                onclick = link.get('onclick', '') or ''
                target_str = href + onclick
                
                match = goload_pattern.search(target_str)
                if match:
                    filepath = match.group(1)   # 예: '20260227/'
                    uuid_file = match.group(2)  # 예: 'EF44F467-347F-4935-00EF-11156CD0AF0F.hwp'
                    file_type = match.group(3)   # 예: 'bid'
                    orig_name = match.group(4)   # 예: '원본파일명.hwp'
                    
                    download_url = (
                        f"{self.KG2B_DOWNLOAD_BASE}"
                        f"?file={urllib.parse.quote(uuid_file)}"
                        f"&filepath={urllib.parse.quote(filepath)}"
                        f"&type={urllib.parse.quote(file_type)}"
                        f"&name={urllib.parse.quote(orig_name)}"
                    )
                    
                    logger.info(f"KG2B Downloading: {orig_name}")
                    p = FileExtractor.download_file(self.session, download_url, item.bid_num, orig_name)
                    if p:
                        item.attached_files.append(p)
                        t = FileExtractor.extract_text(p)
                        if t and "미지원" not in t:
                            texts.append(t)
            
            if texts:
                item.extracted_text = "\n\n".join(texts)
                
        except Exception as e:
            logger.error(f"KG2B _download_kg2b_files error ({item.bid_num}): {e}")


    def parse_award_detail(self, item: AuctionItem) -> AuctionItem:
        """KG2B 낙찰 결과 상세 추출 (사업자번호, 투찰금액 등)"""
        bid_code = item.bid_num.replace('kg2b_', '')
        url = f"https://www.kg2b.com/user/bid_list/bidResultView2.action?bidcode={bid_code}"
        
        try:
            headers = {
                'Referer': 'https://www.kg2b.com/',
                'Sec-Fetch-Site': 'same-origin'
            }
            for attempt in range(3):
                try:
                    time.sleep(random.uniform(3.0, 6.0))
                    response = self.session.get(url, headers=headers, timeout=(15, 30), verify=False)
                    response.raise_for_status()
                    break
                except Exception as e:
                    if attempt < 2:
                        wait_t = 10 * (attempt + 1)
                        logger.warning(f"KG2B parse_award_detail delay ({item.bid_num}), retrying in {wait_t}s ...")
                        time.sleep(wait_t)
                    else:
                        raise e
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 낙찰자 행 찾기 (tr.trpoint_red 가 낙찰자)
            award_row = soup.find('tr', class_='trpoint_red')
            
            # 만약 class가 없다면 순위 1인 행 찾기 (Fallback)
            if not award_row:
                rows = soup.select('table.list_table tbody tr')
                for row in rows:
                    cells = row.find_all('td')
                    if cells and '1' in cells[0].get_text(strip=True):
                        award_row = row
                        break
            
            if award_row:
                cells = award_row.find_all('td')
                if len(cells) >= 7:
                    item.won_biz_num = self.normalize_text(cells[1].get_text())
                    item.won_company = self.normalize_text(cells[2].get_text())
                    raw_amount = cells[4].get_text(strip=True)
                    # 금액에서 숫자만 추출 (예: 15,386,700 원 -> 15386700)
                    item.won_amount = re.sub(r'[^0-9]', '', raw_amount)
                    item.won_result = self.normalize_text(cells[6].get_text())
                    item.status = ItemStatus.WON
                    logger.info(f"KG2B Winner Parsed: {item.won_company} / {item.won_amount}")
            else:
                # 낙찰자가 없는 경우 (유찰 등) 상태만 업데이트
                self.update_status_by_text(item, item.status_text)
                logger.info(f"KG2B No winner row found for {item.bid_num}. Status: {item.status}")

        except Exception as e:
            logger.error(f"KG2B parse_award_detail error ({item.bid_num}): {e}")
            
        return item

    def _extract_text(self, item: AuctionItem, soup: BeautifulSoup):
        """본문 텍스트 추출 및 정제"""
        from packages.core.file_extractor import FileExtractor
        # 상세 페이지의 주요 컨텐츠 영역 (예: .view_cont, .con_txt 등)
        content_area = soup.find(class_=re.compile(r'(view_cont|con_txt|detail_cont)'))
        if content_area:
            text = content_area.get_text(separator='\n', strip=True)
        else:
            text = soup.get_text(separator='\n', strip=True)
            
        item.extracted_text = text[:FileExtractor.MAX_TEXT_LENGTH]
