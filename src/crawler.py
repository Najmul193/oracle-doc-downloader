from __future__ import annotations

import asyncio
import logging
from collections import deque
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


logger = logging.getLogger("oracle-doc-downloader")


class DocumentationCrawler:
    def __init__(self, start_url: str, max_concurrent: int = 5):
        self.start_url = start_url
        self.max_concurrent = max_concurrent
        self._visited_urls: set[str] = set()
        self._pdf_links: set[str] = set()
        self._pdf_referrers: dict[str, str] = {}
        parsed_start = urlparse(start_url)
        self._base_domain = parsed_start.netloc
        # Use the directory portion of the path as the allowed prefix (lowercase)
        path = parsed_start.path.rstrip("/")
        last_slash = path.rfind("/")
        self._allowed_path_prefix = (path[: last_slash + 1] if last_slash > 0 else "/").lower()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "DocumentationCrawler":
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, read=60.0),
            headers={"User-Agent": "Mozilla/5.0 (compatible; oracle-doc-downloader/1.0)"},
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()

    def _is_under_allowed_path(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc != self._base_domain:
            return False
        return parsed.path.lower().startswith(self._allowed_path_prefix)

    def _extract_pdf_links(self, html: str, base_url: str) -> set[str]:
        pdfs: set[str] = set()
        soup = BeautifulSoup(html, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            absolute_url = urljoin(base_url, href)
            parsed = urlparse(absolute_url)

            if parsed.netloc == self._base_domain:
                path = parsed.path.lower()
                if path.endswith(".pdf") and path.startswith(self._allowed_path_prefix):
                    pdfs.add(absolute_url)

        return pdfs

    def _extract_page_links(self, html: str, base_url: str) -> set[str]:
        pages: set[str] = set()
        soup = BeautifulSoup(html, "html.parser")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            absolute_url = urljoin(base_url, href)

            if self._should_follow_link(absolute_url):
                pages.add(absolute_url)

        return pages

    def _should_follow_link(self, url: str) -> bool:
        if not self._is_under_allowed_path(url):
            return False

        path = urlparse(url).path.lower()
        extensions_to_skip = {".zip", ".exe", ".tar.gz", ".jpg", ".png", ".gif", ".pdf"}

        for ext in extensions_to_skip:
            if path.endswith(ext):
                return False

        return True

    async def _crawl_page(self, url: str) -> tuple[set[str], set[str]]:
        pdfs: set[str] = set()
        next_pages: set[str] = set()

        if self._client is None:
            return pdfs, next_pages

        try:
            response = await self._client.get(url)
            response.raise_for_status()

            html = response.text
            pdfs = self._extract_pdf_links(html, url)
            next_pages = self._extract_page_links(html, url)

            logger.debug(f"Found {len(pdfs)} PDFs and {len(next_pages)} links on {url}")

        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")

        return pdfs, next_pages

    async def crawl(self) -> tuple[list[tuple[str, str | None]], int]:
        if self._client is None:
            raise RuntimeError("Crawler not initialized in async context")

        pages_crawled = await self._crawl_bfs()

        pdf_list: list[tuple[str, str | None]] = []
        for pdf_url in self._pdf_links:
            referrer = self._pdf_referrers.get(pdf_url)
            pdf_list.append((pdf_url, referrer))

        return pdf_list, pages_crawled

    async def _crawl_bfs(self) -> int:
        if self._client is None:
            return 0

        to_visit: deque[str] = deque([self.start_url])
        crawled_count = 0

        while to_visit and crawled_count < 1000:
            url = to_visit.popleft()

            if url in self._visited_urls:
                continue

            self._visited_urls.add(url)
            crawled_count += 1
            logger.info(f"Crawling: {url}")

            pdfs, next_pages = await self._crawl_page(url)

            for pdf in pdfs:
                if pdf not in self._pdf_links:
                    self._pdf_links.add(pdf)
                    self._pdf_referrers[pdf] = url

            for next_url in next_pages:
                if next_url not in self._visited_urls:
                    to_visit.append(next_url)

        return crawled_count