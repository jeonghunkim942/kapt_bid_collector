import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

#################################################################
# 구글 시트 연동 설정
#################################################################

# 1. API 사용을 위한 인증 스코프(Scope)
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]

# 2. 로컬 또는 GitHub Actions에서 받아올 JSON 키 경로 및 시트 ID
# GitHub Actions에서는 워크플로우를 통해 client_secret.json 파일이 생성됨
JSON_KEY_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'client_secret.json')
SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')

def get_google_sheet():
    """
    gspread 클라이언트를 통해 구글 스프레드시트의 첫 번째 워크시트 객체를 반환합니다.
    인증 파일이 없거나 시트 ID가 없으면 None을 반환합니다.
    """
    if not os.path.exists(JSON_KEY_PATH):
        print(f"[Sheets Info] 인증 키 파일({JSON_KEY_PATH})을 찾을 수 없습니다.")
        return None
    
    if not SHEET_ID:
        print("[Sheets Info] 환경 변수 GOOGLE_SHEET_ID가 설정되지 않았습니다.")
        return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_PATH, SCOPES)
        client = gspread.authorize(creds)
        
        # SHEET_ID 로 스프레드시트 열기
        spreadsheet = client.open_by_key(SHEET_ID)
        worksheet = spreadsheet.sheet1
        return worksheet
    except Exception as e:
        print(f"[Sheets Error] 구글 시트 연결 중 오류 발생: {e}")
        return None


KG2B_PENDING_SHEET_NAME = "KG2B 미수집"
KG2B_PENDING_COLUMNS = ["입찰마감일", "물건번호", "입찰제목", "상세페이지"]

def get_kg2b_pending_sheet():
    """
    'KG2B 미수집' 시트탭을 반환합니다. 없으면 새로 생성합니다.
    """
    if not os.path.exists(JSON_KEY_PATH) or not SHEET_ID:
        return None

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_PATH, SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SHEET_ID)

        # 기존 시트탭 찾기
        try:
            ws = spreadsheet.worksheet(KG2B_PENDING_SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            # 시트탭이 없으면 새로 생성하고 헤더 추가
            ws = spreadsheet.add_worksheet(title=KG2B_PENDING_SHEET_NAME, rows=1000, cols=len(KG2B_PENDING_COLUMNS))
            ws.append_row(KG2B_PENDING_COLUMNS, value_input_option='USER_ENTERED')
            print(f"[Sheets] '{KG2B_PENDING_SHEET_NAME}' 시트탭 생성 완료")
        return ws
    except Exception as e:
        print(f"[Sheets Error] KG2B 미수집 시트 연결 중 오류: {e}")
        return None


def append_kg2b_pending(kg2b_items_list):
    """
    KG2B 미수집 물건들을 'KG2B 미수집' 시트탭에 저장합니다.
    중복 물건번호는 추가하지 않습니다.
    
    :param kg2b_items_list: [{'close_date': ..., 'bid_num': ..., 'title': ..., 'link': ...}, ...]
    """
    if not kg2b_items_list:
        return

    ws = get_kg2b_pending_sheet()
    if not ws:
        return

    try:
        # 기존 물건번호 조회 (중복 방지)
        existing_records = ws.get_all_records()
        existing_bid_nums = {str(r.get('물건번호', '')) for r in existing_records}

        rows_to_insert = []
        for item in kg2b_items_list:
            if str(item['bid_num']) not in existing_bid_nums:
                rows_to_insert.append([
                    item['close_date'],
                    item['bid_num'],
                    item['title'],
                    item['link'],
                ])

        if rows_to_insert:
            ws.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
            print(f"[Sheets] KG2B 미수집 {len(rows_to_insert)}건을 '{KG2B_PENDING_SHEET_NAME}' 시트에 저장했습니다.")
        else:
            print(f"[Sheets] KG2B 미수집 시트에 새로 추가할 항목이 없습니다 (모두 중복).")
    except Exception as e:
        print(f"[Sheets Error] KG2B 미수집 저장 중 오류: {e}")

def get_existing_state(worksheet):
    """
    구글 시트에서 기존 데이터(입찰마감일, 물건번호)를 읽어옵니다.
    반환값: (last_date_str, existing_bid_nums_set)
    """
    if not worksheet:
        return None, set()
        
    try:
        records = worksheet.get_all_records()
        if not records:
            return None, set()
            
        existing_bid_nums = {str(r.get('물건번호', '')) for r in records if r.get('물건번호')}
        
        # 마지막 입찰마감일 찾기 ('YYYY-MM-DD' 형태)
        dates = [str(r.get('입찰마감일', ''))[:10] for r in records if r.get('입찰마감일')]
        valid_dates = [d for d in dates if len(d) == 10 and d.startswith('20')]
        last_date = max(valid_dates) if valid_dates else None
        
        return last_date, existing_bid_nums
    except Exception as e:
        print(f"[Sheets Error] 기존 데이터 상태 로드 중 오류: {e}")
        return None, set()

def append_to_sheet(worksheet, new_rows_list_of_dicts, columns):
    """
    여러 건의 dict 형태 데이터를 구글 스프레드시트의 하단에 일괄 삽입(Append)합니다.
    
    :param worksheet: gspread 워크시트 객체
    :param new_rows_list_of_dicts: 저장할 데이타 dict 리스트
    :param columns: 구글 시트의 헤더이자 딕셔너리의 키 리스트 (순서 보장)
    """
    if not worksheet or not new_rows_list_of_dicts:
        return
        
    try:
        # 기존 데이터를 불러와서 물건번호-응찰회사명 기준 중복 체크 (선택 사항)
        # 단, 실시간 대용량 처리를 위해선 DB가 더 빠름. 여기선 간단한 중복만 검사
        try:
            existing_records = worksheet.get_all_records()
            existing_keys = {(str(r.get('물건번호', '')), str(r.get('응찰회사명', ''))) for r in existing_records}
        except Exception:
            existing_keys = set()
            
        rows_to_insert = []
        for row in new_rows_list_of_dicts:
            key = (str(row.get('물건번호', '')), str(row.get('응찰회사명', '')))
            if key not in existing_keys:
                # columns 순서대로 리스트화
                row_list = [str(row.get(col, "")) for col in columns]
                rows_to_insert.append(row_list)
                
        if rows_to_insert:
            # 일괄 추가 (Append)
            worksheet.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
            print(f"[Sheets Success] 구글 스프레드시트에 신규 {len(rows_to_insert)}건 저장 완료!")
        else:
            print("[Sheets Info] 구글 스프레드시트에 새로 추가할(중복 제외) 데이터가 없습니다.")
            
    except Exception as e:
        print(f"[Sheets Error] 구글 시트 데이터 저장 중 오류 발생: {e}")
