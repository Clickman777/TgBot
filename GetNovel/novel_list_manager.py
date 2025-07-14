import os
import json
import logging
from typing import Dict, Any

from .models import Novel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class NovelListManager:
    """Handles reading from and writing to the novel_list.json file."""

    def __init__(self, novels_list_path: str = 'GetNovel/Novels/novel_list.json'):
        self.novels_list_path = novels_list_path
        self.logger = logging.getLogger(__name__)
        self._ensure_directory_exists()

    def _ensure_directory_exists(self):
        """Ensures the directory for the novel list exists."""
        os.makedirs(os.path.dirname(self.novels_list_path), exist_ok=True)

    def _load_novels_data(self) -> Dict[str, Any]:
        """Loads the novel data from the JSON file."""
        if not os.path.exists(self.novels_list_path):
            return {}
        try:
            with open(self.novels_list_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError):
            return {}

    def update_novel_list(self, novel: Novel):
        """Updates the central novel list with downloaded chapter info."""
        novels_data = self._load_novels_data()
        
        novel_title_key = novel.title
        existing_chapters = novels_data.get(novel_title_key, {}).get('chapters', [])
        
        newly_downloaded_chapters = [ch.number for ch in novel.chapters]
        
        all_chapters = sorted(list(set(existing_chapters + newly_downloaded_chapters)))
        
        novels_data[novel_title_key] = {
            'title': novel.title,
            'author': novel.author,
            'url': novel.url,
            'cover_url': novel.cover_url,
            'total_chapters': novel.total_chapters,
            'genres': novel.genres,
            'description': novel.description,
            'chapters': all_chapters
        }

        try:
            with open(self.novels_list_path, 'w', encoding='utf-8') as f:
                json.dump(novels_data, f, indent=4)
            self.logger.info(f"Updated novel_list.json for {novel.title}")
        except IOError as e:
            self.logger.error(f"Error updating novel_list.json for {novel.title}: {e}")

    def get_last_downloaded_chapter(self, novel_title: str) -> int:
        """Gets the number of the last downloaded chapter for a novel."""
        novels_data = self._load_novels_data()
        chapters = novels_data.get(novel_title, {}).get('chapters', [])
        return max(chapters) if chapters else 0

    def get_downloaded_chapter_count(self, novel_title: str) -> int:
        """Counts the number of downloaded chapter files for a novel."""
        novel_chapters_dir = os.path.join('GetNovel', 'Novels', novel_title, 'chapters')
        if not os.path.isdir(novel_chapters_dir):
            return 0
        try:
            return len([
                name for name in os.listdir(novel_chapters_dir)
                if os.path.isfile(os.path.join(novel_chapters_dir, name))
            ])
        except OSError as e:
            self.logger.error(f"Error accessing chapter directory for {novel_title}: {e}")
            return 0