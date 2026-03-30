name: Distribute Packages

on:
  push:
    paths:
      - 'packages.csv'
  workflow_dispatch:

jobs:
  process-changes:
    runs-on: windows-latest # Required for WingetCreate and Choco tools
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 2 # Required to compare with previous commit

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      - name: Install Dependencies
        run: |
          pip install pandas requests

      - name: Detect Changed Rows and Run Distribution
        shell: bash
        env:
          GH_PAT: ${{ secrets.GH_PAT }}
          CHOCO_API_KEY: ${{ secrets.CHOCO_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python scripts/distribute.py
