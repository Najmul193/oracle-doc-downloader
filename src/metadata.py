from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class PDFMetadata:
    original_url: str
    downloaded_filename: str
    original_filename: str
    page_title: str | None
    download_timestamp: str
    sha256_checksum: str
    file_size: int


@dataclass
class DownloadReport:
    total_pages_crawled: int = 0
    total_pdfs_found: int = 0
    total_pdfs_downloaded: int = 0
    skipped_files: int = 0
    failed_downloads: int = 0
    crawl_duration_seconds: float = 0.0


class MetadataManager:
    def __init__(self, metadata_dir: Path, download_dir: Path):
        self.metadata_dir = metadata_dir
        self.download_dir = download_dir
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._downloaded_urls: set[str] = set()
        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        checkpoint_file = self.metadata_dir / ".checkpoint.json"
        if checkpoint_file.exists():
            try:
                data = json.loads(checkpoint_file.read_text())
                self._downloaded_urls = set(data.get("downloaded_urls", []))
            except (json.JSONDecodeError, OSError):
                self._downloaded_urls = set()

    def save_checkpoint(self) -> None:
        checkpoint_file = self.metadata_dir / ".checkpoint.json"
        data = {"downloaded_urls": sorted(self._downloaded_urls)}
        checkpoint_file.write_text(json.dumps(data, indent=2))

    def is_downloaded(self, url: str) -> bool:
        return url in self._downloaded_urls

    def mark_downloaded(self, url: str) -> None:
        self._downloaded_urls.add(url)

    def save(
        self,
        pdf_url: str,
        downloaded_name: str,
        original_name: str,
        page_title: str | None,
        file_path: Path,
    ) -> PDFMetadata:
        from utils import get_sha256  # type: ignore

        metadata = PDFMetadata(
            original_url=pdf_url,
            downloaded_filename=downloaded_name,
            original_filename=original_name,
            page_title=page_title,
            download_timestamp=datetime.now().isoformat(),
            sha256_checksum=get_sha256(file_path),
            file_size=file_path.stat().st_size,
        )

        metadata_file = self.metadata_dir / f"{downloaded_name}.json"
        metadata_file.write_text(json.dumps(metadata.__dict__, indent=2))

        return metadata

    def save_report(self, report: DownloadReport) -> None:
        report_file = self.metadata_dir / "report.json"
        report_file.write_text(json.dumps(report.__dict__, indent=2))