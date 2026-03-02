import urllib3
import pandas as pd
from main import create_session, scrape_awarded_list, get_bidders, get_kg2b_bidders, COLUMNS

urllib3.disable_warnings()

def test_first_5_items():
    date_str = "2025-09-03"
    print(f"=== {date_str} 기준 5개 물건 상세조회 테스트 ===")
    
    session = create_session()
    
    # 목록 조회
    items = scrape_awarded_list(session, date_str)
    
    if not items:
        print("목록을 가져오지 못했습니다. (IP가 일시 차단되었거나 서버 오류일 수 있습니다)")
        return
        
    print(f"총 {len(items)}개의 결과 중 상위 5개만 조회합니다.\n")
    
    total_new_rows = []
    
    # 5개만 슬라이싱
    for idx, item in enumerate(items[:5], 1):
        bid_num = item['bid_num']
        close_date = item['close_date']
        title = item['title']
        bid_method = item['bid_method']
        
        print(f"[{idx}/5] {title[:50]} (입찰번호: {bid_num})")
        
        # 상세 조회
        if bid_num.startswith('kg2b_'):
            detail_method, bidders = get_kg2b_bidders(session, bid_num)
        else:
            detail_method, bidders = get_bidders(session, bid_num)
            
        final_bid_method = detail_method if detail_method else bid_method
        
        if not bidders:
            print("  -> 응찰회사 정보 없음")
            continue
            
        print(f"  -> {len(bidders)}개의 응찰회사 정보 발견. 최종 낙찰방법: {final_bid_method}")
        
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
            
    print("\n=== 테스트 결과 데이터 생성 완료 ===")
    df = pd.DataFrame(total_new_rows)
    # 컬럼 순서 지정
    df = df[COLUMNS]
    
    print(f"\n총 {len(df)}건의 데이터가 수집되었습니다.")
    if not df.empty:
        # 결과를 보기 좋게 출력
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df.head(15).to_string())
        
        # 파일로도 저장
        test_file = "bidders_test_5items.csv"
        df.to_csv(test_file, index=False, encoding='utf-8-sig')
        print(f"\nTest 결괏값이 {test_file} 로 저장되었습니다.")

if __name__ == "__main__":
    test_first_5_items()
