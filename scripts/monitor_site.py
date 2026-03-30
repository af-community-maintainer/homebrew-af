import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

TARGET_URL = "https://www.archform.com/downloadarchform-e5r6t7yiughvb"
CSV_PATH = "packages.csv"

def extract_version(url):
    match = re.search(r'_(\d+_\d+_\d+_\d+)\.', url)
    return match.group(1).replace('_', '.') if match else None

def scrape_latest():
    try:
        response = requests.get(TARGET_URL, timeout=20)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True)]
        
        found = {}
        for link in links:
            if '_win_' in link and '.zip' in link:
                version = extract_version(link)
                if '_dpa_' in link:
                    found['dpa'] = {'version': version, 'url': link}
                elif '_cnc_' not in link:
                    found['standard'] = {'version': version, 'url': link}
        return found
    except Exception as e:
        print(f"Scrape failed: {e}")
        return {}

def update_csv(latest_data):
    df = pd.read_csv(CSV_PATH)
    changed = False

    for edition, data in latest_data.items():
        idx = df.index[df['edition'] == edition].tolist()
        if idx:
            current_ver = str(df.at[idx[0], 'version'])
            if current_ver != data['version']:
                print(f"Updating {edition}: {current_ver} -> {data['version']}")
                df.at[idx[0], 'version'] = data['version']
                df.at[idx[0], 'source_url_win'] = data['url']
                changed = True
            
    if changed:
        df.to_csv(CSV_PATH, index=False)

if __name__ == "__main__":
    updates = scrape_latest()
    if updates:
        update_csv(updates)
