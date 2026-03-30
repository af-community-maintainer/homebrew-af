import pandas as pd
import os
import subprocess
import requests
import hashlib
import yaml
import shutil
import stat

# Path to the official Winget repo
WINGET_REPO = "microsoft/winget-pkgs"

def remove_readonly(func, path, excinfo):
    """
    Error handler for shutil.rmtree to handle read-only files on Windows.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)

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
    # AppName should be concise. 'ArchForm' or 'ArchForm CNC'
    app_name = f"ArchForm {edition.capitalize()}" if edition != 'standard' else "ArchForm"
    pkg_id = f"{publisher}.{edition.upper()}" if edition != 'standard' else f"{publisher}.{publisher}"
    
    sha256 = get_sha256(url)
    
    # 1. Version Manifest
    version_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "DefaultLocale": "en-US",
        "ManifestType": "version",
        "ManifestVersion": "1.6.0"
    }

    # 2. Installer Manifest
    # Note: For ZIP files, NestedInstallerType is MANDATORY.
    # We assume 'portable' as these are zip-based distributions.
    installer_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "InstallerLocale": "en-US",
        "MinimumOSVersion": "10.0.0.0",
        "InstallerType": "zip", 
        "NestedInstallerType": "portable",
        "Installers": [{
            "Architecture": "x64",
            "InstallerUrl": url,
            "InstallerSha256": sha256,
            "NestedInstallerFiles": [{
                "RelativeFilePath": f"{publisher}.exe", # Best guess for entry point
                "PortableCommandAlias": publisher
            }]
        }],
        "ManifestType": "installer",
        "ManifestVersion": "1.6.0"
    }

    # 3. Default Locale Manifest
    locale_manifest = {
        "PackageIdentifier": pkg_id,
        "PackageVersion": version,
        "PackageLocale": "en-US",
        "Publisher": publisher,
        "PublisherUrl": "https://archform.com",
        "PrivacyUrl": "https://www.archform.com/privacy-policy",
        "Author": publisher,
        "PackageName": app_name,
        "PackageUrl": "https://archform.com",
        "License": "Proprietary",
        "ShortDescription": desc,
        "Description": desc,
        "Tags": ["orthodontics", "dental", "design"],
        "ManifestType": "defaultLocale",
        "ManifestVersion": "1.6.0"
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

    os.environ["GH_TOKEN"] = token

    subprocess.run(["git", "config", "--global", "user.name", "Community Maintainer"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "maintainer@example.com"], check=True)

    owner = os.environ.get('GITHUB_REPOSITORY_OWNER')
    if not owner:
        repo_slug = os.environ.get('GITHUB_REPOSITORY')
        if repo_slug and '/' in repo_slug:
            owner = repo_slug.split('/')[0]

    if not owner:
        print("Querying GitHub API for current user...")
        owner_result = subprocess.run(["gh", "api", "user", "--privileged", "--query", "login"], capture_output=True, text=True)
        owner = owner_result.stdout.strip().replace('"', '')

    if not owner:
        print("Error: Could not determine repository owner.")
        return

    print(f"Context: Identified owner as '{owner}'")
    
    df = pd.read_csv('packages.csv')
    
    for _, row in df.iterrows():
        edition = row['edition'].lower()
        version = str(row['version'])
        url = row['source_url_win']
        desc = row['description']
        
        pkg_id, ver, manifests = generate_manifests(edition, version, url, desc)
        print(f"\n--- Processing initial onboarding for {pkg_id} ---")

        # Partition is the first letter of the publisher
        first_letter = pkg_id[0].lower()
        # id_path uses the dot-separated segments as folders
        id_path = pkg_id.replace('.', '/')
        base_path = f"manifests/{first_letter}/{id_path}/{ver}"
        
        print(f"Ensuring fork of {WINGET_REPO} exists...")
        subprocess.run(["gh", "repo", "fork", WINGET_REPO, "--clone=false"], check=False)
        
        repo_dir = f"winget-pkgs-{pkg_id.replace('.', '-')}"
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, onexc=remove_readonly)
            
        print(f"Cloning fork from {owner}/winget-pkgs...")
        authenticated_url = f"https://x-access-token:{token}@github.com/{owner}/winget-pkgs.git"
        
        try:
            subprocess.run(["git", "clone", "--depth", "1", authenticated_url, repo_dir], check=True)
        except subprocess.CalledProcessError:
            print(f"Clone failed for {owner}/winget-pkgs.")
            continue

        os.chdir(repo_dir)
        
        branch_name = f"onboard-{pkg_id}-{ver}".replace('.', '-').lower()
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        
        full_manifest_path = os.path.join(os.getcwd(), base_path)
        os.makedirs(full_manifest_path, exist_ok=True)
        
        # Write the 3-file manifest set
        for m_type, content in manifests.items():
            filename = f"{pkg_id}.{m_type}.yaml"
            with open(os.path.join(full_manifest_path, filename), "w") as f:
                # Ensure no flow style (pure block YAML) as required by Winget
                yaml.dump(content, f, sort_keys=False, default_flow_style=False)
        
        print(f"Committing manifests for {pkg_id}...")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", f"Add {pkg_id} version {ver}"], check=True)
        
        print("Pushing to fork...")
        subprocess.run(["git", "push", "origin", branch_name, "--force"], check=True)
        
        print("Creating Pull Request...")
        pr_cmd = [
            "gh", "pr", "create",
            "--title", f"Add {pkg_id} version {ver}",
            "--body", f"Initial onboarding for {pkg_id} generated by community automation. Verified against 1.6.0 schema.",
            "--repo", WINGET_REPO,
            "--head", f"{owner}:{branch_name}"
        ]
        
        result = subprocess.run(pr_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            if "already exists" in result.stderr:
                print(f"PR for {pkg_id} already exists. Skipping.")
            else:
                print(f"Error creating PR for {pkg_id}: {result.stderr}")
        else:
            print(f"Successfully created PR: {result.stdout.strip()}")
        
        os.chdir("..")
        shutil.rmtree(repo_dir, onexc=remove_readonly)
        print(f"Finished {pkg_id} onboarding session.\n")

if __name__ == "__main__":
    main()
