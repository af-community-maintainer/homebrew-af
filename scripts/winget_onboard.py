import pandas as pd
import os
import subprocess
import requests
import hashlib
import yaml
import shutil

# Path to the official Winget repo
WINGET_REPO = "microsoft/winget-pkgs"

def get_sha256(url):
    print(f"Downloading and hashing: {url}")
    response = requests.get(url, stream=True)
    response.raise_for_status()
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
        "InstallerType": "zip", 
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

    return pkg_id, version, {
        "version": version_manifest,
        "installer": installer_manifest,
        "locale": locale_manifest
    }

def main():
    token = os.environ.get('GH_PAT')
    if not token:
        print("Error: GH_PAT environment variable not found.")
        return

    # Configure Git identity
    subprocess.run(["git", "config", "--global", "user.name", "Community Maintainer"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "af-community-maintainer@proton.me"], check=True)

    # Set environment variable for GitHub CLI
    os.environ["GH_TOKEN"] = token
    
    df = pd.read_csv('packages.csv')
    
    for _, row in df.iterrows():
        edition = row['edition'].lower()
        version = str(row['version'])
        url = row['source_url_win']
        desc = row['description']
        
        pkg_id, ver, manifests = generate_manifests(edition, version, url, desc)
        print(f"Processing initial onboarding for {pkg_id}...")

        first_letter = pkg_id[0].lower()
        id_path = pkg_id.replace('.', '/')
        base_path = f"manifests/{first_letter}/{id_path}/{ver}"
        
        print(f"Forking {WINGET_REPO}...")
        # Fork but don't clone yet
        subprocess.run(["gh", "repo", "fork", WINGET_REPO, "--clone=false"], check=False)
        
        repo_dir = "winget-pkgs"
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
            
        # Get the current owner (the maintainer account)
        owner_result = subprocess.run(["gh", "api", "user", "--privileged", "--query", "login"], capture_output=True, text=True)
        owner = owner_result.stdout.strip().strip('"')
        
        print(f"Cloning fork from {owner}/winget-pkgs...")
        # Crucial: Use the token in the URL for authenticated push later
        authenticated_url = f"https://x-access-token:{token}@github.com/{owner}/winget-pkgs.git"
        subprocess.run(["git", "clone", "--depth", "1", authenticated_url, repo_dir], check=True)
        
        os.chdir(repo_dir)
        
        branch_name = f"onboard-{pkg_id}-{ver}".replace('.', '-').lower()
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        
        full_manifest_path = os.path.join(os.getcwd(), base_path)
        os.makedirs(full_manifest_path, exist_ok=True)
        
        for m_type, content in manifests.items():
            filename = f"{pkg_id}.{m_type}.yaml"
            with open(os.path.join(full_manifest_path, filename), "w") as f:
                yaml.dump(content, f, sort_keys=False, default_flow_style=False)
        
        print(f"Committing manifests for {pkg_id}...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Add {pkg_id} version {ver}"], check=True)
        
        print("Pushing to fork...")
        # Since the 'origin' URL already contains the token, this will work seamlessly
        subprocess.run(["git", "push", "origin", branch_name, "--force"], check=True)
        
        print("Creating Pull Request...")
        pr_cmd = [
            "gh", "pr", "create",
            "--title", f"Add {pkg_id} version {ver}",
            "--body", f"Initial onboarding for {pkg_id} generated by community automation.",
            "--repo", WINGET_REPO,
            "--head", f"{owner}:{branch_name}"
        ]
        subprocess.run(pr_cmd, check=True)
        
        os.chdir("..")
        shutil.rmtree(repo_dir)
        print(f"Finished {pkg_id}\n")

if __name__ == "__main__":
    main()
