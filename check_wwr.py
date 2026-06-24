import requests
from bs4 import BeautifulSoup

url = "https://weworkremotely.com/remote-jobs/search?term=python"
headers = {"User-Agent": "Mozilla/5.0 (HireMap project)"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Grab the first real job listing container
li = soup.select_one("li.new-listing-container")
print(li.prettify())
