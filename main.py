import os
import json
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# --- CONFIGURATION ---
GOOGLE_SHEET_NAME = "Timeline"  # Change this to match your EXACT Google Sheet name
TARGET_DOMAIN = "jamesvasquezlaw.com/"        # Change this to your website domain

# 1. Load keys from GitHub Environments
serper_api_key = os.environ.get("SERPER_API_KEY")
google_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

if not serper_api_key or not google_creds_json:
    raise ValueError("Missing environment secrets inside GitHub!")

# 2. Authenticate with Google
scope = ["https://google.com", "https://googleapis.com"]
creds_dict = json.loads(google_creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 3. Pull Spreadsheet Data
sheet = client.open(GOOGLE_SHEET_NAME).sheet1
all_rows = sheet.get_all_records()

print(f"Starting tracking sequence for {len(all_rows)} keywords...")

# 4. Loop & Parse
for index, row in enumerate(all_rows, start=2): 
    keyword = row.get("Keyword")
    if not keyword:
        continue
        
    url = "https://serper.dev"
    payload = {"q": keyword, "gl": "us", "hl": "en", "num": 10}
    headers = {"X-API-KEY": serper_api_key, "Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        organic_results = response.get("organic", [])
        
        on_page_one = "No"
        rank_position = "N/A"
        
        for rank, item in enumerate(organic_results, start=1):
            link = item.get("link", "").lower()
            if TARGET_DOMAIN.lower() in link:
                on_page_one = "Yes"
                rank_position = rank
                break
                
        # Update columns B and C dynamically
        sheet.update_cell(index, 2, on_page_one)
        sheet.update_cell(index, 3, rank_position)
        print(f"Checked: {keyword} -> Page 1: {on_page_one} (Pos: {rank_position})")
        
        # Sleep 1.2 seconds to stay safely within Google Sheets write pacing limits
        time.sleep(1.2)
        
    except Exception as e:
        print(f"Error checking '{keyword}': {e}")

print("Weekly rank check completed successfully!")
