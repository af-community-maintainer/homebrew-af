import pandas as pd
import subprocess
import os
import hashlib
import requests
import json
import base64

def get_sha256(url):
    """Downloads the file to calculate SHA256 (Required for Homebrew and Zip validation)"""
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

def setup_winget_create():
    """Downloads wingetcreate if not present (Windows Runner)"""
    if not os.path.exists("wingetcreate.exe"):
        url = "https://github.com/microsoft/winget-create/releases/latest/download/wingetcreate.exe"
        r = requests.get(url)
        with open("wingetcreate.exe", "wb") as f:
            f.write(r.content)

def submit_winget(edition, version, url, desc):
    pkg_id = f"ArchForm.{edition.upper()}" if edition != 'standard' else "ArchForm.ArchForm"
    print(f"Submitting {pkg_id} v{version} to Winget...")
    setup_winget_create()
    # Note: If this is the first time submitting this ID, 'update' might fail.
    # Manual 'wingetcreate new' might be required once for new IDs.
    cmd = f".\\wingetcreate.exe update {pkg_id} --version {version} --urls {url} --token {os.environ['GH_PAT']}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"Winget Error: {result.stderr}")

def submit_chocolatey(edition, version, url, desc):
    pkg_id = f"archform-{edition}" if edition != 'standard' else "archform"
    print(f"Submitting {pkg_id} v{version} to Chocolatey (Zip Install)...")
    
    nuspec = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">
  <metadata>
    <id>{pkg_id}</id>
    <version>{version}</version>
    <title>ArchForm {edition.capitalize()}</title>
    <authors>ArchForm</authors>
    <owners>Community Maintainer</owners>
    <projectUrl>https://archform.com</projectUrl>
    <description>{desc}</description>
    <tags>orthodontics dental design</tags>
  </metadata>
  <files>
    <file src="tools\**" target="tools" />
  </files>
</package>"""

    os.makedirs("tools", exist_ok=True)
    # Using Install-ChocolateyZipPackage for .zip sources
    install_script = f"""
$packageName = '{pkg_id}'
$url = '{url}'
$zipFileName = '{pkg_id}_{version}.zip'

$packageArgs = @{{
  packageName   = $packageName
  unzipLocation = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)"
  url           = $url
  softwareName  = 'ArchForm'
}}

Install-ChocolateyZipPackage @packageArgs
"""
    with open(os.path.join("tools", "chocolateyinstall.ps1"), "w") as f:
        f.write(install_script)
    with open(f"{pkg_id}.nuspec", "w") as f:
        f.write(nuspec)
    
    # Pack and push using Choco CLI (available on windows-latest)
    subprocess.run(f"choco pack {pkg_id}.nuspec", shell=True)
    # Find the generated nupkg
    nupkg = [f for f in os.listdir(".") if f.endswith(".nupkg")][0]
    push_cmd = f"choco push {nupkg} --api-key {os.environ['CHOCO_API_KEY']} --source https://push.chocolatey.org/ --force"
    subprocess.run(push_cmd, shell=True)
    
    # Cleanup
    os.remove(f"{pkg_id}.nuspec")
    os.remove(nupkg)

def submit_homebrew(edition, version, win_url, desc):
    if edition == 'dpa': 
        print("Skipping Homebrew for DPA (Windows only).")
        return
    
    mac_url = win_url.replace('_win_', '_mac_')
    print(f"Generating Homebrew Cask for {edition}...")
    sha = get_sha256(mac_url)
    if not sha: return

    cask_id = f"archform-{edition}" if edition != 'standard' else "archform"
    token = os.environ['GH_PAT']
    repo_full_name = os.environ.get('GITHUB_REPOSITORY') # Format: "owner/repo"
    
    cask_content = f"""cask "{cask_id}" do
  version "{version}"
  sha256 "{sha}"

  url "{mac_url}"
  name "ArchForm {edition.capitalize()}"
  desc "{desc}"
  homepage "https://archform.com"

  app "ArchForm.app"
end
"""
    # Use GitHub API to push the Cask file to your tap repository
    path = f"Casks/{cask_id}.rb"
    api_url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Check if the file already exists to get its blob SHA (required for updates)
    res = requests.get(api_url, headers=headers)
    existing_sha = res.json().get('sha') if res.status_code == 200 else None
    
    payload = {
        "message": f"update {cask_id} to {version}",
        "content": base64.b64encode(cask_content.encode()).decode(),
    }
    if existing_sha:
        payload["sha"] = existing_sha
    
    put_res = requests.put(api_url, headers=headers, data=json.dumps(payload))
    if put_res.status_code in [200, 201]:
        print(f"Successfully updated {cask_id} in Homebrew Tap.")
    else:
        print(f"Failed to push to Homebrew Tap: {put_res.text}")

def main():
    # Force generic identity for all Git/Metadata operations
    subprocess.run(['git', 'config', 'user.name', 'Community Maintainer'], check=True)
    subprocess.run(['git', 'config', 'user.email', 'maintainer@example.com'], check=True)

    try:
        df = pd.read_csv('packages.csv')
        for _, row in df.iterrows():
            ver = str(row['version'])
            win_url = row['source_url_win']
            edition = row['edition'].lower()
            desc = row['description']

            # Execute submissions
            submit_winget(edition, ver, win_url, desc)
            submit_chocolatey(edition, ver, win_url, desc)
            submit_homebrew(edition, ver, win_url, desc)
            
    except Exception as e:
        print(f"Workflow execution failed: {e}")

if __name__ == "__main__":
    main()
