from __future__ import annotations

from pathlib import Path

import httpx
from bs4 import BeautifulSoup


class PDFRenamer:
    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self.http_client = http_client or httpx.AsyncClient()

    async def __aenter__(self) -> "PDFRenamer":
        return self

    async def __aexit__(self, *args) -> None:
        if self.http_client:
            await self.http_client.aclose()

    async def extract_pdf_title(self, file_path: Path) -> str | None:
        try:
            import PyPDF2

            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                if reader.metadata and "Title" in reader.metadata:
                    title = reader.metadata["Title"]
                    if isinstance(title, str) and title.strip():
                        return title.strip()
        except Exception:
            pass
        return None

    async def get_page_title(self, url: str) -> str | None:
        try:
            response = await self.http_client.get(url, timeout=30.0)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                return title_tag.string.strip()
        except Exception:
            pass
        return None

    async def determine_filename(
        self,
        pdf_path: Path,
        original_url: str,
        referring_page_url: str | None = None,
    ) -> str:
        from utils import normalize_filename

        # Use the original URL filename first (it's unique and descriptive)
        original_name = Path(original_url).name
        if original_name:
            return normalize_filename(original_name)

        # Fall back to PDF metadata title
        title = await self.extract_pdf_title(pdf_path)
        if title:
            return normalize_filename(title)

        # Fall back to referring page title
        if referring_page_url:
            page_title = await self.get_page_title(referring_page_url)
            if page_title:
                return normalize_filename(page_title)

        return normalize_filename("downloaded_document")

    async def find_referring_page(self, pdf_url: str, all_urls: set[str]) -> str | None:
        for url in all_urls:
            if url.endswith(".html") or url.endswith(".htm"):
                try:
                    response = await self.http_client.get(url, timeout=10.0)
                    if pdf_url in response.text:
                        return url
                except Exception:
                    continue
        return None