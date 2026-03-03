import urllib3
urllib3.disable_warnings()
from main import create_session, get_kg2b_bidders

print("Testing get_kg2b_bidders with the new patch...")
session = create_session()
bid_method, bidders = get_kg2b_bidders(session, 'kg2b_125278')
print("Status:", "Success" if len(bidders) > 0 else "Failed")
print("Bidders found:", len(bidders))
for b in bidders:
    print(b)
