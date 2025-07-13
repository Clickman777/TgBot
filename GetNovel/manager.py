import os
import json
import concurrent.futures
from typing import Optional

from .scraper import Scraper
from .epub import EpubGenerator
from .models import Novel, Chapter
from bs4 import BeautifulSoup, Tag

class NovelManager:
    """Orchestrates the entire process of scraping and generating a novel."""

    def __init__(self):
        self.scraper = Scraper()
        self.epub_generator = EpubGenerator()

    def download_chapter(self, chapter_num: int, novel: Novel) -> Optional[Chapter]:
        """
        Downloads a single chapter if it doesn't exist locally,
        saves it to a file, and returns a Chapter object.
        """
        if not novel.base_chapter_url or not novel.novel_dir:
            return None

        chapter_path = os.path.join(novel.novel_dir, 'chapters', f'chapter_{chapter_num}.html')
        chapter_url = novel.base_chapter_url.format(chapter_num)

        # Check if chapter already exists
        if os.path.exists(chapter_path):
            try:
                with open(chapter_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Try to parse the title from the existing HTML file
                soup = BeautifulSoup(content, 'html.parser')
                title_tag = soup.find('h1')
                title = title_tag.text if title_tag else f"Chapter {chapter_num}"
                
                print(f"Chapter {chapter_num} already exists locally.")
                return Chapter(
                    number=chapter_num,
                    title=title,
                    content=content,
                    url=chapter_url
                )
            except IOError as e:
                print(f"Error reading existing chapter {chapter_num}: {e}")
                # Proceed to re-download
        
        # If not found locally, download it
        chapter_data = self.scraper.get_chapter_content(chapter_url)
        
        if chapter_data:
            title, content = chapter_data
            # Prepend the title to the content for storage
            content_to_save = f"<h1>{title}</h1>\n{content}"
            try:
                with open(chapter_path, 'w', encoding='utf-8') as f:
                    f.write(content_to_save)
                print(f"Successfully downloaded and saved Chapter {chapter_num}")
                return Chapter(
                    number=chapter_num,
                    title=title,
                    content=content, # Return content without the h1 tag
                    url=chapter_url
                )
            except IOError as e:
                print(f"Error saving chapter {chapter_num} to file: {e}")
                return None
        else:
            print(f"Failed to download Chapter {chapter_num}")
            return None

    def update_novel_list_json(self, novel: Novel):
        """Updates the central novel list with downloaded chapter info."""
        novels_list_path = os.path.join('GetNovel', 'Novels', 'novel_list.json')
        
        os.makedirs(os.path.dirname(novels_list_path), exist_ok=True)

        if os.path.exists(novels_list_path):
            try:
                with open(novels_list_path, 'r', encoding='utf-8') as f:
                    novels_data = json.load(f)
            except (IOError, json.JSONDecodeError):
                novels_data = {}
        else:
            novels_data = {}

        novel_title_key = novel.title
        existing_chapters = novels_data.get(novel_title_key, {}).get('chapters', [])
        
        newly_downloaded_chapters = [ch.number for ch in novel.chapters]
        
        all_chapters = sorted(list(set(existing_chapters + newly_downloaded_chapters)))
        
        novels_data[novel_title_key] = {
            'title': novel.title,
            'chapters': all_chapters
        }

        try:
            with open(novels_list_path, 'w', encoding='utf-8') as f:
                json.dump(novels_data, f, indent=4)
            print(f"Updated novel_list.json for {novel.title}")
        except IOError as e:
            print(f"Error updating novel_list.json: {e}")

    def process_novel(self, url: str, start_chapter: int, end_chapter: Optional[int] = None) -> Optional[str]:
        """
        Main method to process a novel from URL to EPUB.
        
        1. Fetches novel metadata, checking for existing local data first.
        2. Creates directory structure under GetNovel/Novels and saves metadata.
        3. Downloads chapters concurrently.
        4. Updates the central novel_list.json.
        5. Downloads cover image.
        6. Generates the EPUB file.
        
        Returns the path to the generated EPUB, or None on failure.
        """
        # 1. Get Novel Info
        temp_novel = self.scraper.get_novel_info(url)
        if not temp_novel:
            print(f"Could not retrieve initial info for novel at {url}")
            return None
        
        base_novels_dir = os.path.join('GetNovel', 'Novels')
        
        novel_dir_name = temp_novel.title
        novel_dir = os.path.join(base_novels_dir, novel_dir_name)
        metadata_path = os.path.join(novel_dir, 'metadata.json')
        
        if os.path.exists(metadata_path):
            print("Found existing metadata. Loading from file.")
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                novel = Novel(**metadata)
                novel.novel_dir = novel_dir
            except (IOError, json.JSONDecodeError, TypeError) as e:
                print(f"Error reading metadata file: {e}. Re-fetching from web.")
                novel = temp_novel
        else:
            novel = temp_novel

        if not novel:
             return None
        
        # 2. Create directory structure and save/update metadata
        novel.novel_dir = novel_dir
        chapters_dir = os.path.join(novel.novel_dir, 'chapters')
        os.makedirs(chapters_dir, exist_ok=True)

        metadata_to_save = {
            "title": novel.title,
            "author": novel.author,
            "url": novel.url,
            "cover_url": novel.cover_url,
            "total_chapters": novel.total_chapters,
            "base_chapter_url": novel.base_chapter_url
        }
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_to_save, f, indent=4)

        # 3. Determine chapter range, load existing, and download missing
        if end_chapter is None:
            end_chapter = novel.total_chapters or start_chapter
        
        requested_chapters_range = range(start_chapter, end_chapter + 1)
        
        novel.chapters = []
        existing_chapter_numbers = set()

        # First, load all existing chapters in the range from local files
        for i in requested_chapters_range:
            chapter_path = os.path.join(novel.novel_dir, 'chapters', f'chapter_{i}.html')
            if os.path.exists(chapter_path):
                try:
                    with open(chapter_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # When loading from file, extract title from the <h1> tag
                    soup = BeautifulSoup(content, 'html.parser')
                    title_tag = soup.find('h1')
                    if title_tag and isinstance(title_tag, Tag):
                        title = title_tag.text
                        # Remove the h1 tag from the content before passing it on
                        title_tag.decompose()
                        # Get the remaining HTML as a string
                        remaining_content = str(soup)
                    else:
                        title = f"Chapter {i}"
                        remaining_content = content

                    chapter = Chapter(
                        number=i,
                        title=title,
                        content=remaining_content,
                        url=novel.base_chapter_url.format(i) if novel.base_chapter_url else ""
                    )
                    novel.chapters.append(chapter)
                    existing_chapter_numbers.add(i)
                    print(f"Loaded existing Chapter {i} from file.")
                except IOError as e:
                    print(f"Error reading existing chapter {i}, will re-download: {e}")

        # Determine which chapters are missing and need to be downloaded
        chapters_to_download = [i for i in requested_chapters_range if i not in existing_chapter_numbers]

        if chapters_to_download:
            print(f"Downloading missing chapters: {chapters_to_download}")
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_chapter = {
                    executor.submit(self.download_chapter, i, novel): i for i in chapters_to_download
                }
                for future in concurrent.futures.as_completed(future_to_chapter):
                    result = future.result()
                    if result:
                        novel.chapters.append(result)

        # 4. Update novel_list.json with all chapters for this operation
        self.update_novel_list_json(novel)

        if not novel.chapters:
            print("Failed to download or load any chapters for the requested range. Aborting.")
            return None
            
        # 5. Download Cover
        self.scraper.download_cover_image(novel)

        # 6. Generate EPUB
        epub_path = self.epub_generator.create_epub(novel)

        return epub_path