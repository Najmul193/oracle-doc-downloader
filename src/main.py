from __future__ import annotations

import asyncio
import time
from pathlib import Path

from crawler import DocumentationCrawler
from downloader import PDFDownloader
from metadata import MetadataManager, DownloadReport
from utils import setup_logging


async def main(start_url: str, base_dir: Path | None = None) -> DownloadReport:
    base_dir = base_dir or Path.cwd()
    download_dir = base_dir / "downloads"
    metadata_dir = base_dir / "metadata"
    log_dir = base_dir / "logs"

    logger = setup_logging(log_dir)
    logger.info(f"Starting oracle-doc-downloader with URL: {start_url}")

    report = DownloadReport()
    start_time = time.time()

    metadata_manager = MetadataManager(metadata_dir, download_dir)

    async with DocumentationCrawler(start_url) as crawler:
        pdf_links, pages_crawled = await crawler.crawl()
        report.total_pages_crawled = pages_crawled
        report.total_pdfs_found = len(pdf_links)
        logger.info(f"Found {len(pdf_links)} PDF links from {pages_crawled} pages")

    async with PDFDownloader(download_dir, metadata_dir, max_concurrent=5) as downloader:
        results = await downloader.download_all(pdf_links, metadata_manager)
        report.total_pdfs_downloaded = downloader.downloaded_count
        report.skipped_files = downloader.skipped_count

    report.crawl_duration_seconds = round(time.time() - start_time, 2)
    report.failed_downloads = downloader.failed_count

    metadata_manager.save_report(report)

    logger.info(f"Download complete. Report saved to {metadata_dir / 'report.json'}")
    return report


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python main.py <start_url>")
        sys.exit(1)

    url = sys.argv[1]
    report = asyncio.run(main(url))
    print(f"Total PDFs downloaded: {report.total_pdfs_downloaded}")