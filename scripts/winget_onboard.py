import pandas as pd
import os
import subprocess
import requests
import hashlib
import yaml

# Path to the official Winget repo
WINGET_REPO = "microsoft/winget-pkgs"

def get_sha256(url):
    response = requests.get(url, stream=True)
    sha256_hash = hashlib.sha256()
    for byte_block in response.iter_content(4096):
        sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def generate_manifests(edition, version, url, desc):
    publisher = "ArchForm"
    name = f"ArchForm {edition.capitalize()}"
    pkg_id = f"{publisher}.{edition.upper()}" if edition != 'standard' else f"{publisher}.{publisher}"
    
    sha256 = get_sha256(url)
    
    # 1. Version Manifest
    version_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "DefaultLocale": "en-US",
        "ManifestType": "version",
        "ManifestVersion": "1.4.0"
    }

    # 2. Installer Manifest
    installer_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "InstallerLocale": "en-US",
        "MinimumOSVersion": "10.0.0.0",
        "InstallerType": "zip", # We are using the zip links provided
        "Installers": [{
            "Architecture": "x64",
            "InstallerUrl": url,
            "InstallerSha256": sha256
        }],
        "ManifestType": "installer",
        "ManifestVersion": "1.4.0"
    }

    # 3. Default Locale Manifest
    locale_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "PackageLocale": "en-US",
        "Publisher": publisher,
        "PackageName": name,
        "ShortDescription": desc,
        "License": "Proprietary",
        "ManifestType": "defaultLocale",
        "ManifestVersion": "1.4.0"
    }

    # 4. Singleton/Global Manifest (Optional for multi-file, but we'll use the 3-file pattern)
    return pkg_id, version, {
        "version": version_manifest,
        "installer": installer_manifest,
        "locale": locale_manifest
    }

def main():
    token = os.environ.get('GH_PAT')
    if not token:
        print("GH_PAT not found.")
        return

    # Auth GitHub CLI
    subprocess.run(f"echo {token} | gh auth login --with-token", shell=True, check=True)
    
    df = pd.read_csv('packages.csv')
    
    for _, row in df.iterrows():
        edition = row['edition'].lower()
        version = str(row['version'])
        url = row['source_url_win']
        desc = row['description']
        
        pkg_id, ver, manifests = generate_manifests(edition, version, url, desc)
        print(f"Onboarding {pkg_id}...")

        # Create path: manifests/a/ArchForm/Edition/Version
        # Winget uses first letter of ID for the first folder
        first_letter = pkg_id[0].lower()
        base_path = f"manifests/{first_letter}/{pkg_id.replace('.', '/')}/{ver}"
        
        # Fork and Clone Winget Repo (shallow clone for speed)
        branch_name = f"onboard-{pkg_id}-{ver}".replace('.', '-')
        subprocess.run(f"gh repo fork {WINGET_REPO} --clone --depth 1", shell=True)
        
        os.chdir("winget-pkgs")
        subprocess.run(f"git checkout -b {branch_name}", shell=True)
        
        os.makedirs(base_path, exist_ok=True)
        
        # Write files
        for m_type, content in manifests.items():
            filename = f"{pkg_id}.{m_type}.yaml"
            with open(os.path.join(base_path, filename), "w") as f:
                yaml.dump(content, f, sort_keys=False)
        
        # Commit and Push
        subprocess.run("git add .", shell=True)
        subprocess.run(f'git commit -m "Add {pkg_id} version {ver}"', shell=True)
        subprocess.run(f"git push origin {branch_name}", shell=True)
        
        # Create PR
        subprocess.run(f'gh pr create --title "Add {pkg_id} version {ver}" --body "Initial onboarding for {pkg_id}." --repo {WINGET_REPO}', shell=True)
        
        # Cleanup for next row
        os.chdir("..")
        subprocess.run("rmdir /s /q winget-pkgs", shell=True)

if __name__ == "__main__":
    main()
