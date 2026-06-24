import requests
import json

url = "https://remoteok.com/api"
headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
resp = requests.get(url, headers=headers, timeout=15)
data = resp.json()

print("Total items returned:", len(data))
print("\n--- First item (usually metadata) ---")
print(json.dumps(data[0], indent=2)[:600])
print("\n--- Second item (first real job) ---")
print(json.dumps(data[1], indent=2)[:800])
