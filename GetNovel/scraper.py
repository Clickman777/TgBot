import requests
from bs4 import BeautifulSoup, Tag
import re
import os
import shutil
import concurrent.futures
from typing import List, Optional
from .models import Novel

class Scraper:
    """Handles all web scraping operations for novels."""

    def __init__(self, base_url: str = "https://novelfire.net"):
        self.base_url = base_url
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def get_novel_info(self, url: str) -> Optional[Novel]:
        """Scrapes the novel's main page to get metadata and returns a Novel object."""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching novel page {url}: {e}")
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        try:
            title_element = soup.find('h1', class_='novel-title')
            title = title_element.text.strip() if isinstance(title_element, Tag) else "Unknown Title"

            author = "N/A"
            author_element = soup.find('div', class_='author')
            if isinstance(author_element, Tag):
                author_tag = author_element.find('a')
                if isinstance(author_tag, Tag):
                    author = author_tag.text.strip()

            cover_url = None
            cover_element = soup.find('div', class_='fixed-img')
            if isinstance(cover_element, Tag):
                img_tag = cover_element.find('img')
                if isinstance(img_tag, Tag):
                    cover_url = img_tag.get('data-src') or img_tag.get('src')

            total_chapters = None
            stats_div = soup.find('div', class_='header-stats')
            if isinstance(stats_div, Tag):
                chapters_span = stats_div.find('span')
                if isinstance(chapters_span, Tag):
                    strong_tag = chapters_span.find('strong')
                    if isinstance(strong_tag, Tag):
                        match = re.search(r'(\d+)', strong_tag.text)
                        if match:
                            total_chapters = int(match.group(1))

            return Novel(
                title=title,
                author=author,
                url=url,
                cover_url=str(cover_url) if cover_url else None,
                total_chapters=total_chapters,
                base_chapter_url=f"{url}/chapter-{{}}"
            )
        except Exception as e:
            print(f"Failed to parse novel information from {url}: {e}")
            return None

    def download_cover_image(self, novel: Novel) -> Optional[str]:
        """Downloads the cover image for a given novel and updates the novel object."""
        if not novel.cover_url or not novel.novel_dir:
            return None
        
        file_extension = os.path.splitext(novel.cover_url)[1]
        if file_extension not in ['.jpg', '.jpeg', '.png', '.webp']:
            file_extension = '.jpg'
            
        save_path = os.path.join(novel.novel_dir, f"cover{file_extension}")

        if os.path.exists(save_path):
            novel.local_cover_path = save_path
            return save_path

        try:
            response = requests.get(novel.cover_url, stream=True, timeout=10)
            response.raise_for_status()
            os.makedirs(novel.novel_dir, exist_ok=True)
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            novel.local_cover_path = save_path
            return save_path
        except requests.exceptions.RequestException as e:
            print(f"Error downloading cover: {e}")
            return None

    def get_chapter_content(self, chapter_url: str) -> Optional[str]:
        """Fetches and parses the content of a single chapter."""
        try:
            response = requests.get(chapter_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            content_div = soup.find('div', id='content')
            if isinstance(content_div, Tag):
                return "".join([str(p) for p in content_div.find_all('p')])
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error fetching chapter {chapter_url}: {e}")
            return None

    def get_ranked_list(self, sort_type='overall') -> List[Novel]:
        """Scrapes the ranking page and returns a list of Novel objects."""
        sort_map = {
            'overall': self.base_url + '/ranking',
            'most-read': self.base_url + '/ranking/most-read',
            'most-review': self.base_url + '/ranking/most-review'
        }
        url = sort_map.get(sort_type, sort_map['overall'])

        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching ranking page: {e}")
            return []

        soup = BeautifulSoup(response.content, 'html.parser')
        rank_ul = soup.find('ul', class_='rank-novels')

        if not isinstance(rank_ul, Tag):
            print("Could not find the ranking list element ('ul.rank-novels').")
            return []

        covers_dir = "ranking_covers"
        if os.path.exists(covers_dir):
            shutil.rmtree(covers_dir)
        os.makedirs(covers_dir)

        novel_list: List[Novel] = []
        novel_items = rank_ul.find_all('li', class_='novel-item', limit=10)

        for i, novel_item in enumerate(novel_items):
            if not isinstance(novel_item, Tag):
                continue

            title_element = novel_item.find('h2', class_='title')
            cover_element = novel_item.find('div', class_='cover-wrap')

            if not isinstance(title_element, Tag) or not isinstance(cover_element, Tag):
                continue
            
            title_anchor = title_element.find('a')
            if not isinstance(title_anchor, Tag):
                continue

            novel_url_path = title_anchor.get('href')
            if not isinstance(novel_url_path, str):
                continue
            
            novel_url = novel_url_path if novel_url_path.startswith('http') else self.base_url + novel_url_path
            title = title_anchor.text.strip()
            
            cover_url = None
            img_tag = cover_element.find('img')
            if isinstance(img_tag, Tag):
                cover_url = img_tag.get('data-src')

            local_cover_path = None
            if isinstance(cover_url, str):
                try:
                    cover_response = requests.get(cover_url, headers=self.headers, timeout=10)
                    cover_response.raise_for_status()
                    
                    content_type = cover_response.headers.get('Content-Type', '')
                    ext = '.jpg' # default
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    
                    local_cover_path = os.path.join(covers_dir, f"cover_{i}{ext}")
                    with open(local_cover_path, 'wb') as f:
                        f.write(cover_response.content)
                except requests.exceptions.RequestException:
                    local_cover_path = None
            
            novel_list.append(Novel(
                title=title,
                author='N/A',
                url=novel_url,
                cover_url=str(cover_url) if cover_url else None,
                local_cover_path=local_cover_path
            ))

        # Fetch author details concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_novel = {executor.submit(self.get_novel_info, novel.url): novel for novel in novel_list}
            for future in concurrent.futures.as_completed(future_to_novel):
                novel_data = future.result()
                original_novel = future_to_novel[future]
                if novel_data:
                    original_novel.author = novel_data.author
                    original_novel.total_chapters = novel_data.total_chapters
        
        return novel_list