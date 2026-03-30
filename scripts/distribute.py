import pandas as pd
import subprocess
import os
import hashlib
import requests
import json
import base64

def get_sha256(url):
    """Downloads the file to calculate SHA256 (Required for Security)"""
    print(f"Calculating SHA256 for: {url}")
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
    if not os.path.exists("wingetcreate.exe"):
        url = "https://github.com/microsoft/winget-create/releases/latest/download/wingetcreate.exe"
        r = requests.get(url)
        with open("wingetcreate.exe", "wb") as f:
            f.write(r.content)

def submit_winget(edition, version, url, desc):
    pkg_id = f"ArchForm.{edition.upper()}" if edition != 'standard' else "ArchForm.ArchForm"
    print(f"Submitting {pkg_id} v{version} to Winget...")
    setup_winget_create()
    cmd = f".\\wingetcreate.exe update {pkg_id} --version {version} --urls {url} --token {os.environ['GH_PAT']}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)

def submit_chocolatey(row, version):
    edition = row['edition'].lower()
    url = row['source_url_win']
    pkg_id = f"archform-{edition}" if edition != 'standard' else "archform"
    
    print(f"Submitting {pkg_id} v{version} to Chocolatey...")
    
    checksum = get_sha256(url)
    if not checksum:
        print(f"Skipping Chocolatey for {pkg_id} due to hash failure.")
        return

    # Metadata from CSV
    summary = row.get('summary', row['description'])
    icon_url = row.get('icon_url', '')
    license_url = row.get('license_url', '')
    project_url = row.get('homepage', 'https://archform.com')
    docs_url = row.get('docs_url', '')
    mailing_list_url = row.get('mailing_list_url', '')
    project_source_url = row.get('project_source_url', '')
    
    repo_url = f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'community/repo')}"

    nuspec = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">
  <metadata>
    <id>{pkg_id}</id>
    <version>{version}</version>
    <title>ArchForm {edition.capitalize()}</title>
    <authors>ArchForm</authors>
    <owners>Community Maintainer</owners>
    <licenseUrl>{license_url}</licenseUrl>
    <projectUrl>{project_url}</projectUrl>
    <iconUrl>{icon_url}</iconUrl>
    <requireLicenseAcceptance>false</requireLicenseAcceptance>
    <description>{row['description']}</description>
    <summary>{summary}</summary>
    <releaseNotes>{project_url}</releaseNotes>
    <tags>archform orthodontics dental design {edition}</tags>
    <packageSourceUrl>{repo_url}</packageSourceUrl>
    <docsUrl>{docs_url}</docsUrl>
    <mailingListUrl>{mailing_list_url}</mailingListUrl>
    <projectSourceUrl>{project_source_url}</projectSourceUrl>
  </metadata>
  <files>
    <file src="tools\\**" target="tools" />
  </files>
</package>"""

    os.makedirs("tools", exist_ok=True)
    install_script = rf"""
$packageName = '{pkg_id}'
$url = '{url}'
$packageArgs = @{{
  packageName   = $packageName
  unzipLocation = "$(Split-Path -Parent $MyInvocation.MyCommand.Definition)"
  url           = $url
  softwareName  = 'ArchForm'
  checksum      = '{checksum}'
  checksumType  = 'sha256'
}}

Install-ChocolateyZipPackage @packageArgs
"""
    with open(os.path.join("tools", "chocolateyinstall.ps1"), "w") as f:
        f.write(install_script)
    with open(f"{pkg_id}.nuspec", "w") as f:
        f.write(nuspec)
    
    subprocess.run(f"choco pack {pkg_id}.nuspec", shell=True)
    nupkgs = [f for f in os.listdir(".") if f.endswith(".nupkg")]
    if nupkgs:
        nupkg = nupkgs[0]
        subprocess.run(f"choco push {nupkg} --api-key {os.environ['CHOCO_API_KEY']} --source https://push.chocolatey.org/ --force", shell=True)
        os.remove(nupkg)
    os.remove(f"{pkg_id}.nuspec")

def submit_homebrew(edition, version, win_url, desc):
    if edition == 'dpa': return
    mac_url = win_url.replace('_win_', '_mac_')
    sha = get_sha256(mac_url)
    if not sha: return

    cask_id = f"archform-{edition}" if edition != 'standard' else "archform"
    token = os.environ['GH_PAT']
    repo_full_name = os.environ.get('GITHUB_REPOSITORY')
    
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
    path = f"Casks/{cask_id}.rb"
    api_url = f"https://api.github.com/repos/{repo_full_name}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    
    res = requests.get(api_url, headers=headers)
    existing_sha = res.json().get('sha') if res.status_code == 200 else None
    
    payload = {
        "message": f"update {cask_id} to {version}",
        "content": base64.b64encode(cask_content.encode()).decode(),
    }
    if existing_sha: payload["sha"] = existing_sha
    requests.put(api_url, headers=headers, data=json.dumps(payload))

def main():
    subprocess.run(['git', 'config', '--global', 'user.name', 'Community Maintainer'], check=True)
    subprocess.run(['git', 'config', '--global', 'user.email', 'maintainer@example.com'], check=True)

    try:
        df = pd.read_csv('packages.csv')
        for _, row in df.iterrows():
            ver = str(row['version'])
            win_url = row['source_url_win']
            edition = row['edition'].lower()
            desc = row['description']

            submit_winget(edition, ver, win_url, desc)
            submit_chocolatey(row, ver)
            submit_homebrew(edition, ver, win_url, desc)
            
    except Exception as e:
        print(f"Workflow failed: {e}")

if __name__ == "__main__":
    main()
