import urllib.request
import json
import time

accounts = [439530, 10295233, 11296062]
url = 'http://127.0.0.1:5000/api/test_trade'

for acct in accounts:
    print(f"Testing account {acct}...")
    data = json.dumps({"login": acct}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=130) as response:
            res_data = response.read()
            print(f"Result: {json.loads(res_data)}")
    except Exception as e:
        print(f"Failed: {e}")
