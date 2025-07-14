import os
import logging
import concurrent.futures
from typing import Optional

from .scraper import Scraper
from .models import Novel, Chapter
from .exceptions import ChapterDownloadError
from bs4 import BeautifulSoup, Tag

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ChapterManager:
    """Handles downloading, saving, and loading of novel chapters."""

    def __init__(self, scraper: Scraper):
        self.scraper = scraper
        self.logger = logging.getLogger(__name__)

    def _load_chapter_from_local(self, chapter_path: str, chapter_num: int, chapter_url: str) -> Optional[Chapter]:
        if not os.path.exists(chapter_path):
            return None
        try:
            with open(chapter_path, 'r', encoding='utf-8') as f:
                content = f.read()
            soup = BeautifulSoup(content, 'html.parser')
            title_tag = soup.find('h1')
            title = title_tag.text if title_tag else f"Chapter {chapter_num}"
            self.logger.info(f"Chapter {chapter_num} already exists locally.")
            return Chapter(number=chapter_num, title=title, content=content, url=chapter_url)
        except IOError as e:
            self.logger.error(f"Error reading existing chapter {chapter_num}: {e}")
            return None

    def _download_and_save_chapter(self, chapter_num: int, novel: Novel, chapter_path: str, chapter_url: str) -> Chapter:
        chapter_data = self.scraper.get_chapter_content(chapter_url)
        if not chapter_data:
            raise ChapterDownloadError(f"Failed to download Chapter {chapter_num}")

        title, content = chapter_data
        content_to_save = f"<h1>{title}</h1>\n{content}"
        try:
            os.makedirs(os.path.dirname(chapter_path), exist_ok=True)
            with open(chapter_path, 'w', encoding='utf-8') as f:
                f.write(content_to_save)
            self.logger.info(f"Successfully downloaded and saved Chapter {chapter_num}")
            return Chapter(
                number=chapter_num,
                title=title,
                content=content,
                url=chapter_url
            )
        except IOError as e:
            raise ChapterDownloadError(f"Error saving chapter {chapter_num} to file: {e}") from e

    def download_chapter(self, chapter_num: int, novel: Novel) -> Optional[Chapter]:
        """
        Downloads a single chapter, first checking locally, then from the web.
        """
        if not novel.base_chapter_url or not novel.novel_dir:
            return None

        chapter_path = os.path.join(novel.novel_dir, 'chapters', f'chapter_{chapter_num}.html')
        chapter_url = novel.base_chapter_url.format(chapter_num)

        # Try to load from local file first
        local_chapter = self._load_chapter_from_local(chapter_path, chapter_num, chapter_url)
        if local_chapter:
            return local_chapter

        # If not found locally, download it
        try:
            return self._download_and_save_chapter(chapter_num, novel, chapter_path, chapter_url)
        except ChapterDownloadError as e:
            self.logger.error(f"Failed to download and save chapter {chapter_num}: {e}")
            return None

    def load_existing_chapters(self, novel: Novel, requested_chapters_range: range) -> set[int]:
        existing_chapter_numbers = set()
        if not novel.novel_dir or not novel.base_chapter_url:
            return existing_chapter_numbers

        for i in requested_chapters_range:
            chapter_path = os.path.join(novel.novel_dir, 'chapters', f'chapter_{i}.html')
            if os.path.exists(chapter_path):
                try:
                    with open(chapter_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    title_tag = soup.find('h1')
                    if title_tag and isinstance(title_tag, Tag):
                        title = title_tag.text
                        title_tag.decompose()
                        remaining_content = str(soup)
                    else:
                        title = f"Chapter {i}"
                        remaining_content = content
                    
                    chapter = Chapter(
                        number=i, title=title, content=remaining_content,
                        url=novel.base_chapter_url.format(i)
                    )
                    novel.chapters.append(chapter)
                    existing_chapter_numbers.add(i)
                    self.logger.info(f"Loaded existing Chapter {i} from file.")
                except IOError as e:
                    self.logger.error(f"Error reading existing chapter {i}, will re-download: {e}")
        return existing_chapter_numbers

    def download_missing_chapters(self, novel: Novel, chapters_to_download: list[int]):
        if not chapters_to_download:
            return
            
        self.logger.info(f"Downloading missing chapters: {chapters_to_download}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_chapter = {
                executor.submit(self.download_chapter, i, novel): i for i in chapters_to_download
            }
            for future in concurrent.futures.as_completed(future_to_chapter):
                try:
                    result = future.result()
                    if result:
                        novel.chapters.append(result)
                except ChapterDownloadError as e:
                    self.logger.error(f"A chapter download failed: {e}")