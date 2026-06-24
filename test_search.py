import requests
import sys

keyword = sys.argv[1] if len(sys.argv) > 1 else "python developer"
location = sys.argv[2] if len(sys.argv) > 2 else "Bellevue"
deadline = float(sys.argv[3]) if len(sys.argv) > 3 else 12

print(
    f"Searching: keyword='{keyword}', location='{location}', deadline={deadline}s")
resp = requests.post("http://localhost:5000/api/search", json={
    "keyword": keyword,
    "location": location,
    "deadline": deadline,
})

data = resp.json()
print("\n=== RESULT ===")
print(f"search_id:        {data.get('search_id')}")
print(f"total_results:    {data.get('total_results')}")
print(f"completed_sources: {data.get('completed_sources')}")
print(f"sources_with_data: {data.get('sources_with_data')}")
print(f"complete:         {data.get('complete')}")
print("\nFirst 5 jobs:")
for job in data.get("results", [])[:5]:
    print(f"  - [{job['source']}] {job['title']} @ {job['company']}")
