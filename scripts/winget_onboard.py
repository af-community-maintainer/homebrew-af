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
    # Use GH_PAT for API calls, but GITHUB_TOKEN is also often available
    token = os.environ.get('GH_PAT')
    if not token:
        print("Error: GH_PAT environment variable not found.")
        return

    # Configure Git to use the token for HTTPS operations
    # This avoids the 'gh auth login' scope issues
    subprocess.run(["git", "config", "--global", "user.name", "Community Maintainer"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "maintainer@example.com"], check=True)

    # Set environment variable for GitHub CLI to use the token automatically
    os.environ["GH_TOKEN"] = token
    
    df = pd.read_csv('packages.csv')
    
    for _, row in df.iterrows():
        edition = row['edition'].lower()
        version = str(row['version'])
        url = row['source_url_win']
        desc = row['description']
        
        pkg_id, ver, manifests = generate_manifests(edition, version, url, desc)
        print(f"Processing initial onboarding for {pkg_id}...")

        # Winget path structure: manifests/a/ArchForm/Edition/Version
        first_letter = pkg_id[0].lower()
        id_path = pkg_id.replace('.', '/')
        base_path = f"manifests/{first_letter}/{id_path}/{ver}"
        
        # Fork the repo using GitHub CLI (if not already forked)
        print(f"Forking {WINGET_REPO}...")
        subprocess.run(["gh", "repo", "fork", WINGET_REPO, "--clone=false"], check=False)
        
        # Clone the fork (shallow clone for efficiency)
        repo_dir = "winget-pkgs"
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir)
            
        print("Cloning fork...")
        subprocess.run(["gh", "repo", "clone", f"{os.environ.get('GITHUB_REPOSITORY_OWNER')}/winget-pkgs", repo_dir, "--", "--depth", "1"], check=True)
        
        os.chdir(repo_dir)
        
        branch_name = f"onboard-{pkg_id}-{ver}".replace('.', '-').lower()
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        
        # Create directories and write manifests
        full_manifest_path = os.path.join(os.getcwd(), base_path)
        os.makedirs(full_manifest_path, exist_ok=True)
        
        for m_type, content in manifests.items():
            filename = f"{pkg_id}.{m_type}.yaml"
            with open(os.path.join(full_manifest_path, filename), "w") as f:
                yaml.dump(content, f, sort_keys=False, default_flow_style=False)
        
        # Commit and Push
        print(f"Committing manifests for {pkg_id}...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Add {pkg_id} version {ver}"], check=True)
        
        print("Pushing to fork...")
        subprocess.run(["git", "push", "origin", branch_name, "--force"], check=True)
        
        # Create PR to the upstream repo
        print("Creating Pull Request...")
        pr_cmd = [
            "gh", "pr", "create",
            "--title", f"Add {pkg_id} version {ver}",
            "--body", f"Initial onboarding for {pkg_id} generated by community automation.",
            "--repo", WINGET_REPO,
            "--head", f"{os.environ.get('GITHUB_REPOSITORY_OWNER')}:{branch_name}"
        ]
        subprocess.run(pr_cmd, check=True)
        
        # Cleanup for next edition in CSV
        os.chdir("..")
        shutil.rmtree(repo_dir)
        print(f"Finished {pkg_id}\n")

if __name__ == "__main__":
    main()
