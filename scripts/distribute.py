import pandas as pd
import subprocess
import os
import re
import hashlib
import requests

def get_sha256(url):
    """Downloads the file to calculate SHA256 (Required for Homebrew)"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        sha256_hash = hashlib.sha256()
        for byte_block in response.iter_content(4096):
            sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating hash for {url}: {e}")
        return None

def submit_winget(edition, version, url, desc):
    pkg_id = f"ArchForm.{edition.upper()}" if edition != 'standard' else "ArchForm.ArchForm"
    print(f"Submitting {pkg_id} v{version} to Winget...")
    # Example: wingetcreate update ArchForm.CNC --version 2.6.4.13 --urls <url>
    # cmd = f"wingetcreate update {pkg_id} --version {version} --urls {url} --token {os.environ['GH_PAT']}"
    # subprocess.run(cmd, shell=True)

def submit_chocolatey(edition, version, url, desc):
    pkg_id = f"archform-{edition}" if edition != 'standard' else "archform"
    print(f"Submitting {pkg_id} v{version} to Chocolatey...")
    # Logic to generate .nuspec with <authors>Company</authors> but <owners>FakeUser</owners>
    
def submit_homebrew(edition, version, win_url, desc):
    if edition == 'dpa':
        print("Skipping Homebrew for DPA (Windows only).")
        return

    mac_url = win_url.replace('_win_', '_mac_')
    print(f"Generating Homebrew Cask for {edition} using {mac_url}...")
    sha = get_sha256(mac_url)
    if not sha: return

    cask_name = f"archform-{edition}" if edition != 'standard' else "archform"
    cask_content = f"""
cask "{cask_name}" do
  version "{version}"
  sha256 "{sha}"

  url "{mac_url}"
  name "ArchForm {edition.capitalize()}"
  desc "{desc}"
  homepage "https://archform.com"

  app "ArchForm.app"
end
"""
    # Logic to commit this to your 'homebrew-tools' tap repo
    print(f"Cask {cask_name} generated. Ready for push.")

def main():
    # Setup anonymous git identity locally for the session
    subprocess.run(['git', 'config', 'user.name', 'AF Community Maintainer'], check=True)
    subprocess.run(['git', 'config', 'user.email', 'af-community-maintainer@proton.me'], check=True)

    try:
        df = pd.read_csv('packages.csv')
        for _, row in df.iterrows():
            ver = str(row['version'])
            win_url = row['source_url_win']
            edition = row['edition'].lower()
            desc = row['description']

            # Process Windows
            submit_winget(edition, ver, win_url, desc)
            submit_chocolatey(edition, ver, win_url, desc)
            
            # Process Mac
            submit_homebrew(edition, ver, win_url, desc)
            
    except Exception as e:
        print(f"Workflow failed: {e}")

if __name__ == "__main__":
    main()
