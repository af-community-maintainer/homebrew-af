import pandas as pd
import subprocess
import os
import requests

def setup_winget_create():
    if not os.path.exists("wingetcreate.exe"):
        url = "https://github.com/microsoft/winget-create/releases/latest/download/wingetcreate.exe"
        r = requests.get(url)
        with open("wingetcreate.exe", "wb") as f:
            f.write(r.content)

def main():
    setup_winget_create()
    df = pd.read_csv('packages.csv')
    
    for _, row in df.iterrows():
        edition = row['edition'].lower()
        pkg_id = f"ArchForm.{edition.upper()}" if edition != 'standard' else "ArchForm.ArchForm"
        version = str(row['version'])
        url = row['source_url_win']
        desc = row['description']
        
        print(f"Attempting initial onboarding for {pkg_id}...")
        
        # Using 'new' command for initial submission
        new_cmd = (
            f".\\wingetcreate.exe new {url} "
            f"--id {pkg_id} "
            f"--version {version} "
            f"--publisher ArchForm "
            f"--name \"ArchForm {edition.capitalize()}\" "
            f"--description \"{desc}\" "
            f"--license \"Proprietary\" "
            f"--token {os.environ['GH_PAT']} "
            f"--interactive false"
        )
        
        result = subprocess.run(new_cmd, shell=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(f"Error during onboarding {pkg_id}: {result.stderr}")

if __name__ == "__main__":
    main()
