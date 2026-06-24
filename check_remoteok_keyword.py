import requests
import sys

keyword = sys.argv[1] if len(sys.argv) > 1 else "data scientist"
url = "https://remoteok.com/api"
headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
resp = requests.get(url, headers=headers, timeout=15)
print("Status:", resp.status_code)
data = resp.json()
listings = data[1:] if data and isinstance(
    data[0], dict) and "legal" in data[0] else data
print(f"Total jobs in feed: {len(listings)}")

# Show what matches the keyword (title + tags), and a sample of titles that don't
matches = 0
print(f"\nJobs matching '{keyword}':")
for item in listings:
    title = (item.get("position") or item.get("title") or "")
    tags = item.get("tags", []) or []
    haystack = title.lower() + " " + " ".join(tags).lower()
    if keyword.lower() in haystack:
        matches += 1
        print(f"  MATCH: {title} | tags: {tags[:5]}")
print(f"\nTotal matches: {matches} out of {len(listings)} jobs")

print("\nSample of ALL job titles in the feed (first 15):")
for item in listings[:15]:
    print(f"  - {item.get('position') or item.get('title')}")
