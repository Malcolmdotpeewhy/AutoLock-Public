import requests
import json
import os

url = "https://ddragon.leagueoflegends.com/cdn/14.1.1/data/en_US/runesReforged.json"
print(f"Testing download from {url}")

try:
    response = requests.get(url, timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Success! Data Len: {len(data)}")
        with open("cache/runesReforged.json", "w", encoding="utf-8") as f:
            json.dump(data, f)
            print("File saved successfully.")
    else:
        print(f"Failed with status {response.status_code}")
        print(response.text[:200])
except Exception as e:
    print(f"Exception: {e}")
