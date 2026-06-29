import asyncio
from crawler import DocumentationCrawler
from utils import setup_logging


async def test():
    logger = setup_logging()
    async with DocumentationCrawler('https://docs.oracle.com/cd/G27840_01/index.htm') as crawler:
        pdfs, pages = await crawler.crawl()
        print(f'Found {len(pdfs)} PDFs and crawled {pages} pages')
        for pdf, ref in list(pdfs)[:5]:
            print(f'  - {pdf}')


if __name__ == "__main__":
    asyncio.run(test())