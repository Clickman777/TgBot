import os
import concurrent.futures
from typing import Optional

from .scraper import Scraper
from .epub import EpubGenerator
from .models import Novel, Chapter

class NovelManager:
    """Orchestrates the entire process of scraping and generating a novel."""

    def __init__(self):
        self.scraper = Scraper()
        self.epub_generator = EpubGenerator()

    def download_chapter(self, chapter_num: int, novel: Novel) -> Optional[Chapter]:
        """Downloads a single chapter and returns a Chapter object."""
        if not novel.base_chapter_url:
            return None
            
        chapter_url = novel.base_chapter_url.format(chapter_num)
        content = self.scraper.get_chapter_content(chapter_url)
        
        if content:
            print(f"Successfully downloaded Chapter {chapter_num}")
            return Chapter(
                number=chapter_num,
                title=f"Chapter {chapter_num}",
                content=content,
                url=chapter_url
            )
        else:
            print(f"Failed to download Chapter {chapter_num}")
            return None

    def process_novel(self, url: str, start_chapter: int, end_chapter: Optional[int] = None) -> Optional[str]:
        """
        Main method to process a novel from URL to EPUB.
        
        1. Fetches novel metadata.
        2. Downloads chapters concurrently.
        3. Downloads cover image.
        4. Generates the EPUB file.
        
        Returns the path to the generated EPUB, or None on failure.
        """
        # 1. Get Novel Info
        novel = self.scraper.get_novel_info(url)
        if not novel:
            print(f"Could not retrieve information for novel at {url}")
            return None
        
        # Create a directory for the novel based on its title
        novel.novel_dir = novel.title.replace(' ', '_')
        os.makedirs(novel.novel_dir, exist_ok=True)

        # 2. Determine chapter range and download
        if end_chapter is None:
            end_chapter = novel.total_chapters or start_chapter
        
        chapters_to_fetch = range(start_chapter, end_chapter + 1)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_chapter = {
                executor.submit(self.download_chapter, i, novel): i for i in chapters_to_fetch
            }
            for future in concurrent.futures.as_completed(future_to_chapter):
                result = future.result()
                if result:
                    novel.chapters.append(result)
        
        if not novel.chapters:
            print("Failed to download any chapters. Aborting.")
            return None
            
        # 3. Download Cover
        self.scraper.download_cover_image(novel)

        # 4. Generate EPUB
        epub_path = self.epub_generator.create_epub(novel)

        return epub_path