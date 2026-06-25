import requests
r = requests.post("https://hiremap-ffey.onrender.com/api/search",
                  json={"keyword": "python developer",
                        "location": "Seattle", "deadline": 15},
                  timeout=60)
print("API responded:", r.status_code, r.json())
