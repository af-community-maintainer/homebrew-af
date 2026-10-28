import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

TARGET_URL = "https://www.archform.com/downloadarchform-e5r6t7yiughvb"
CSV_PATH = "packages.csv"

def extract_version(url):
    match = re.search(r'_(\d+_\d+_\d+(?:_\d+)?)\.', url)
    return match.group(1).replace('_', '.') if match else None

def probe_cnc(standard_version):
    """CNC isn't listed on the download page; its URL follows the mainline
    version with a .0 suffix (e.g. 2.7.2 -> ArchForm_win_cnc_2_7_2_0.zip)."""
    base = standard_version.replace('.', '_')
    candidates = [
        f"https://download.archform.co/ArchForm_win_cnc_{base}_0.zip",
        f"https://download.archform.co/ArchForm_win_cnc_{base}.zip",
    ]
    for url in candidates:
        try:
            r = requests.get(url, stream=True, timeout=20)
            if r.status_code == 200:
                r.close()
                version = extract_version(url)
                return {'version': version, 'url': url}
            r.close()
        except Exception:
            pass
    return None

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
                elif '_cnc_' in link:
                    found['cnc'] = {'version': version, 'url': link}
                else:
                    found['standard'] = {'version': version, 'url': link}

        if 'standard' in found and found['standard']['version'] and 'cnc' not in found:
            cnc = probe_cnc(found['standard']['version'])
            if cnc:
                found['cnc'] = cnc
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
