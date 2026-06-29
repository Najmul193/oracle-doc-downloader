from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import httpx
from renamer import PDFRenamer  # type: ignore


logger = logging.getLogger("oracle-doc-downloader")


class DownloadResult:
    def __init__(
        self,
        success: bool,
        file_path: Path | None = None,
        error_message: str | None = None,
        skipped: bool = False,
    ):
        self.success = success
        self.file_path = file_path
        self.error_message = error_message
        self.skipped = skipped


class PDFDownloader:
    def __init__(
        self,
        download_dir: Path,
        metadata_dir: Path,
        max_concurrent: int = 3,
        max_retries: int = 3,
    ):
        self.download_dir = download_dir
        self.metadata_dir = metadata_dir
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self._semaphore: asyncio.Semaphore | None = None
        self.http_client: httpx.AsyncClient | None = None
        self.renamer: PDFRenamer | None = None

    async def __aenter__(self) -> "PDFDownloader":
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self.http_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, read=120.0),
        )
        self.renamer = PDFRenamer(self.http_client)
        await self.renamer.__aenter__()
        return self

    async def __aexit__(self, *args) -> None:
        if self.http_client:
            await self.http_client.aclose()
        if self.renamer:
            await self.renamer.__aexit__(*args)

    async def download(
        self,
        pdf_url: str,
        referring_page_url: str | None = None,
    ) -> DownloadResult:
        from utils import is_pdf_valid  # type: ignore

        if self._semaphore is None or self.renamer is None:
            raise RuntimeError("Downloader not initialized in async context")

        async with self._semaphore:
            for attempt in range(self.max_retries):
                try:
                    response = await self.http_client.get(pdf_url)
                    content_type = response.headers.get("content-type", "")

                    if "application/pdf" not in content_type and response.content[:5] != b"%PDF-":
                        logger.warning(
                            f"Invalid content type for {pdf_url}: {content_type}"
                        )
                        return DownloadResult(
                            success=False, error_message=f"Invalid content type: {content_type}"
                        )

                    temp_dir = tempfile.mkdtemp()
                    temp_path = Path(temp_dir) / "temp.pdf"

                    with open(temp_path, "wb") as f:
                        f.write(response.content)

                    if not is_pdf_valid(temp_path):
                        logger.warning(f"Downloaded file is not a valid PDF: {pdf_url}")
                        temp_path.unlink()
                        Path(temp_dir).rmdir()
                        return DownloadResult(success=False, error_message="Invalid PDF file")

                    smart_name = await self.renamer.determine_filename(
                        temp_path, pdf_url, referring_page_url
                    )
                    final_path = self.download_dir / smart_name

                    counter = 1
                    while final_path.exists():
                        stem = Path(smart_name).stem
                        final_path = self.download_dir / f"{stem}_{counter}.pdf"
                        counter += 1

                    temp_path.rename(final_path)
                    self.downloaded_count += 1
                    logger.info(f"Downloaded: {pdf_url} -> {final_path.name}")

                    return DownloadResult(success=True, file_path=final_path)

                except httpx.HTTPStatusError as e:
                    logger.warning(f"HTTP error on attempt {attempt + 1} for {pdf_url}: {e}")
                    if attempt == self.max_retries - 1:
                        self.failed_count += 1
                        return DownloadResult(success=False, error_message=str(e))
                    await asyncio.sleep(2**attempt)

                except Exception as e:
                    logger.error(f"Error downloading {pdf_url}: {e}")
                    if attempt == self.max_retries - 1:
                        self.failed_count += 1
                        return DownloadResult(success=False, error_message=str(e))
                    await asyncio.sleep(2**attempt)

            self.failed_count += 1
            return DownloadResult(success=False, error_message="Max retries exceeded")

    async def download_all(
        self,
        pdf_links: list[tuple[str, str | None]],
        metadata_manager: "MetadataManager",  # type: ignore
    ) -> dict[str, DownloadResult]:
        results: dict[str, DownloadResult] = {}

        async def download_with_check(
            url: str, referring_page: str | None
        ) -> tuple[str, DownloadResult]:
            if metadata_manager.is_downloaded(url):
                self.skipped_count += 1
                logger.info(f"Skipping already downloaded: {url}")
                return url, DownloadResult(success=True, skipped=True)

            result = await self.download(url, referring_page)
            return url, result

        tasks = [
            asyncio.create_task(download_with_check(url, referrer))
            for url, referrer in pdf_links
        ]

        for future in asyncio.as_completed(tasks):
            url, result = await future
            results[url] = result
            if result.success and result.file_path and not result.skipped:
                metadata_manager.mark_downloaded(url)
                metadata_manager.save(
                    pdf_url=url,
                    downloaded_name=result.file_path.name,
                    original_name=Path(url).name,
                    page_title=None,
                    file_path=result.file_path,
                )

        return results