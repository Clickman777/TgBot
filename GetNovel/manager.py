import os
import json
import logging
from typing import Optional

from .scraper import Scraper
from .epub import EpubGenerator
from .models import Novel
from .exceptions import MetadataError
from .chapter_manager import ChapterManager
from .novel_list_manager import NovelListManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NovelManager:
    """Orchestrates the entire process of scraping and generating a novel."""

    def __init__(self):
        self.scraper = Scraper()
        self.epub_generator = EpubGenerator()
        self.chapter_manager = ChapterManager(self.scraper)
        self.novel_list_manager = NovelListManager()
        self.logger = logging.getLogger(__name__)

    def _initialize_novel_data(self, url: str) -> Novel:
        try:
            # Always fetch fresh data to get the latest chapter count
            fresh_novel_data = self.scraper.get_novel_info(url)
            if not fresh_novel_data:
                raise MetadataError(f"Could not retrieve initial info for novel at {url}")

            base_novels_dir = os.path.join('GetNovel', 'Novels')
            novel_dir_name = fresh_novel_data.title
            novel_dir = os.path.join(base_novels_dir, novel_dir_name)
            metadata_path = os.path.join(novel_dir, 'metadata.json')

            if os.path.exists(metadata_path):
                self.logger.info("Found existing metadata. Loading and updating.")
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    
                    # Update total chapters from the fresh scrape
                    metadata['total_chapters'] = fresh_novel_data.total_chapters
                    
                    novel = Novel(**metadata)
                    novel.novel_dir = novel_dir
                    
                    # Update the base chapter URL as well, in case it changes
                    novel.base_chapter_url = fresh_novel_data.base_chapter_url
                    
                    return novel
                except (IOError, json.JSONDecodeError, TypeError) as e:
                    self.logger.error(f"Error reading metadata file: {e}. Using fresh data.")
            
            return fresh_novel_data
        except Exception as e:
            raise MetadataError(f"Failed to initialize novel data: {e}") from e

    def _setup_novel_directories(self, novel: Novel):
        if not novel.novel_dir:
            base_novels_dir = os.path.join('GetNovel', 'Novels')
            novel.novel_dir = os.path.join(base_novels_dir, novel.title)

        chapters_dir = os.path.join(novel.novel_dir, 'chapters')
        os.makedirs(chapters_dir, exist_ok=True)

        metadata_path = os.path.join(novel.novel_dir, 'metadata.json')
        metadata_to_save = {
            "title": novel.title, "author": novel.author, "url": novel.url,
            "cover_url": novel.cover_url, "total_chapters": novel.total_chapters,
            "base_chapter_url": novel.base_chapter_url
        }
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata_to_save, f, indent=4)
        except IOError as e:
            raise MetadataError(f"Failed to save metadata for {novel.title}: {e}") from e

    def update_novel(self, url: str) -> Optional[str]:
        """Checks for new chapters and updates the novel."""
        try:
            novel = self._initialize_novel_data(url)
            self._setup_novel_directories(novel)

            last_downloaded = self.novel_list_manager.get_last_downloaded_chapter(novel.title)
            total_chapters = novel.total_chapters

            if not total_chapters:
                self.logger.warning(f"Could not determine total chapters for {novel.title}. Cannot update.")
                return None

            if last_downloaded >= total_chapters:
                self.logger.info(f"Novel '{novel.title}' is already up to date.")
                return None

            start_chapter = last_downloaded + 1
            end_chapter = total_chapters
            
            self.logger.info(f"Updating '{novel.title}' from chapter {start_chapter} to {end_chapter}.")
            
            return self.process_novel(url, start_chapter, end_chapter)

        except MetadataError as e:
            self.logger.error(f"Could not update novel: {e}")
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred during update: {e}", exc_info=True)
            return None

    def process_novel(self, url: str, start_chapter: int, end_chapter: Optional[int] = None) -> Optional[str]:
        """Main method to process a novel from URL to EPUB."""
        try:
            novel = self._initialize_novel_data(url)
            self._setup_novel_directories(novel)

            if end_chapter is None:
                end_chapter = novel.total_chapters or start_chapter
            
            requested_chapters_range = range(start_chapter, end_chapter + 1)
            
            novel.chapters = []
            existing_chapter_numbers = self.chapter_manager.load_existing_chapters(novel, requested_chapters_range)
            
            chapters_to_download = [i for i in requested_chapters_range if i not in existing_chapter_numbers]
            self.chapter_manager.download_missing_chapters(novel, chapters_to_download)

            self.novel_list_manager.update_novel_list(novel)

            if not novel.chapters:
                self.logger.warning("Failed to download or load any chapters for the requested range. Aborting.")
                return None
            
            self.scraper.download_cover_image(novel)
            epub_path = self.epub_generator.create_epub(novel)
            return epub_path

        except MetadataError as e:
            self.logger.error(f"Could not process novel: {e}")
            return None
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            return None