import sys
sys.path.append(r"f:\프로젝트\경매사이트2")
from scraper import KaptScraper
import urllib3, logging
urllib3.disable_warnings()

# 로거 설정하여 scraper 로그도 확인
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

s = KaptScraper()
items = s.scrape_list(
    start_date="2025-09-01",
    end_date="2025-09-01",
    keyword="",
    search_date_gb="bid",
    bid_type="3",
    bid_state="5"
)
print(f"\n=== Result: {len(items)} items ===")
for item in items[:5]:
    print(f"  {item.bid_num} | {item.title[:40]} | {item.close_date}")
