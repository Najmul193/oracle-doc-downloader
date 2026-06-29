# Oracle Documentation Downloader

Recursively crawl Oracle documentation websites and download PDFs with smart naming.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
python3 src/main.py https://docs.oracle.com/cd/G27840_01/index.htm
```

## Directory Structure

- `downloads/` - Downloaded PDF files
- `metadata/` - Metadata JSON for each PDF and `report.json`
- `logs/` - Execution logs

## Features

- Recursive crawling within the same domain
- Concurrent PDF downloads
- Smart filename extraction (PDF title, page title, etc.)
- Resume support via checkpoint
- SHA256 checksums
- Retry on failures