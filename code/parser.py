import re
import time
import random
import urllib.parse
import urllib3
from bs4 import BeautifulSoup
from .base import BaseParser, logger
from .kg2b_parser import Kg2bParser
from packages.core.models import AuctionItem, ItemStatus
from packages.core.file_extractor import FileExtractor

class KaptParser(BaseParser):
    """K-APT 전용 파서"""
    
    def parse_detail(self, item: AuctionItem) -> AuctionItem:
        """K-APT 상세 정보 및 파일 텍스트 추출"""
        item.status = "PARSING"
        try:
            # 요청 간 대기 (KAPT 차단 방지)
            time.sleep(random.uniform(3.0, 5.0))
            
            # 1. 상세 페이지 HTML 파싱 (Key-Value 필드 추출)
            self._fetch_and_parse_html_details(item)
            
            # 2. 파일 목록 조회 및 다운로드 (KAPT 전용)
            self._parse_kapt_files(item)
            
            if item.attached_files: item.status = "PARSED"
            else: item.status = "PARSED_NO_FILES" if item.office_address else "FAILED"
            
        except Exception as e:
            logger.error(f"KaptParser error ({item.bid_num}): {e}")
            item.status = "FAILED"
        return item

    def _fetch_and_parse_html_details(self, item: AuctionItem):
        """KAPT 상세 HTML 파싱 및 필드 매핑"""
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        try:
            time.sleep(random.uniform(3.0, 5.0))
            # Referer 추가는 세션 유지를 위해 중요
            headers = {'Referer': 'https://www.k-apt.go.kr/'}
            response = self.session.get(item.url, verify=False, timeout=15, headers=headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 본문 텍스트 (Fallback용)
            item.extracted_text = soup.get_text(separator='\n', strip=True)[:FileExtractor.MAX_TEXT_LENGTH]
            
            # 테이블 데이터 추출
            table_data = self.extract_table_data(soup)
            
            # 필드 매핑 보강
            item.apt_name = self.get_value_by_keys(table_data, ['단지명', '발주처', '배주처', '아파트명']) or item.apt_name
            item.office_address = self.get_value_by_keys(table_data, ['관리사무소주소', '관리주체주소', '주소', '소재지'])
            item.phone = self.get_value_by_keys(table_data, ['전화번호', '연락처(TEL)', 'TEL', '문의처'])
            item.fax = self.get_value_by_keys(table_data, ['팩스번호', '연락처(FAX)', 'FAX'])
            
            # 세데수/동수 추출
            scale = self.get_value_by_keys(table_data, ['단지규모', '가구수', '규모'])
            if scale:
                b_match = re.search(r'(\d+)\s*동', scale)
                h_match = re.search(r'(\d+)\s*세대', scale)
                if b_match: item.building_count = int(b_match.group(1))
                if h_match: item.household_count = int(h_match.group(1))

            item.bid_method = self.get_value_by_keys(table_data, ['입찰방법', '입찰방식', '입찰구분'])
            item.bid_title = self.get_value_by_keys(table_data, ['입찰제목', '제목', '공고명']) or item.title
            item.bid_type = self.get_value_by_keys(table_data, ['입찰종류', '경쟁방식'])
            item.bid_category = self.get_value_by_keys(table_data, ['입찰분류', '물품분류'])
            item.bid_submission_date = self.get_value_by_keys(table_data, ['입찰서제출마감일', '입찰마감일시'])
            item.awarding_method_detail = self.get_value_by_keys(table_data, ['낙찰방법', '낙찰자결정방법']) or item.awarding_method

        except Exception as e:
            logger.error(f"KaptParser _fetch_and_parse_html_details error: {e}")

    def _parse_kapt_files(self, item: AuctionItem):
        """K-APT 전용 파일 API 활용 텍스트 추출"""
        try:
            # CSRF 취득을 위한 메인 페이지 조회
            res_main = self.session.get('https://www.k-apt.go.kr/bid/bidList.do', timeout=10, verify=False)
            soup_main = BeautifulSoup(res_main.text, 'html.parser')
            csrf_token = soup_main.find('meta', {'name': '_csrf'}).get('content', '') if soup_main.find('meta', {'name': '_csrf'}) else ''

            # 파일 목록 API 호출
            url_files = 'https://www.k-apt.go.kr/bid/bidFileListData.do?seq=BID_FILE'
            headers = {
                'X-CSRF-TOKEN': csrf_token, 
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json'
            }
            res_files = self.session.post(url_files, headers=headers, json={'bidNum': item.bid_num}, timeout=10, verify=False)
            
            if res_files.status_code == 200:
                # 응답이 XML 형식이므로 BeautifulSoup으로 파싱
                soup_xml = BeautifulSoup(res_files.text, 'html.parser')
                data_tags = soup_xml.find_all('data')
                
                texts = []
                for data_tag in data_tags:
                    seq_tag = data_tag.find('seq')
                    name_tag = data_tag.find('filename')
                    
                    seq = seq_tag.get_text(strip=True) if seq_tag else ''
                    file_name = name_tag.get_text(strip=True) if name_tag else ''
                    
                    if seq and file_name:
                        file_url = f"https://www.k-apt.go.kr/cmm/file/BID/fileDownload.do?key={seq}&fileName={urllib.parse.quote(file_name)}"
                        logger.info(f"Downloading file: {file_name} (seq: {seq})")
                        p = FileExtractor.download_file(self.session, file_url, item.bid_num, file_name)
                        if p:
                            item.attached_files.append(p)
                            t = FileExtractor.extract_text(p)
                            if t and "미지원" not in t: texts.append(t)
                if texts: item.extracted_text = "\n\n".join(texts)
        except Exception as e:
            logger.error(f"KaptParser _parse_kapt_files error: {e}")


    def parse_award_detail(self, item: AuctionItem) -> AuctionItem:
        """K-APT 낙찰정보 파싱 (bidDetail.do 페이지의 참여업체 정보 테이블)"""
        url = f"https://www.k-apt.go.kr/bid/bidDetail.do?bidNum={item.bid_num}"
        try:
            time.sleep(random.uniform(3.0, 5.0))
            response = self.session.get(url, timeout=15, verify=False)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 1. 낙찰/유찰/취소 사유 파싱
            status_th = soup.find('th', string=re.compile(r'낙찰/유찰/취소\s*사유'))
            if status_th:
                status_td = status_th.find_next_sibling('td')
                if status_td:
                    val = status_td.get_text(strip=True)
                    item.won_result = val
            
            # 2. 참여업체 정보 테이블에서 낙찰자 찾기
            # 헤더: 순번(0), 응찰회사(1), 사업자번호(2), 대표자(3), 전화(4),
            #        응찰일시(5), 현장설명참석(6), 서류적정(7), 응찰금액(8), 낙찰여부(9), 낙찰무효(10)
            for table in soup.find_all('table'):
                ths = table.find_all('th')
                th_texts = [th.get_text(strip=True) for th in ths]
                
                # '낙찰여부' 헤더가 있는 테이블 찾기
                if '낙찰여부' not in th_texts:
                    continue
                
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) < 10:
                        continue
                    
                    # 낙찰여부(td[9]) == 'Y' 인 행 찾기
                    award_flag = cells[9].get_text(strip=True)
                    if award_flag == 'Y':
                        item.won_company = cells[1].get_text(strip=True)
                        item.won_biz_num = cells[2].get_text(strip=True)
                        item.won_amount = cells[8].get_text(strip=True).replace(',', '')
                        logger.info(f"KAPT Award found: {item.bid_num} -> {item.won_company} / {item.won_amount}")
                        break
                break  # 참여업체 테이블 처리 후 종료
            
            logger.info(f"KAPT Award parsed: {item.bid_num}")
        except Exception as e:
            logger.error(f"KaptParser parse_award_detail error: {e}")
        return item


class AuctionParser:
    """사이트별 파서를 선택하여 처리를 위임하는 메인 파사드"""
    def __init__(self, session):
        self.kapt = KaptParser(session)
        self.kg2b = Kg2bParser(session)

    def parse_detail(self, item: AuctionItem) -> AuctionItem:
        if item.bid_num.startswith('kg2b_'):
            return self.kg2b.parse_detail(item)
        return self.kapt.parse_detail(item)

    def parse_award_detail(self, item: AuctionItem) -> AuctionItem:
        if item.bid_num.startswith('kg2b_'):
            return self.kg2b.parse_award_detail(item)
        return self.kapt.parse_award_detail(item)
