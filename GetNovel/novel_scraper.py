import os
import requests
from bs4 import BeautifulSoup
import time
import random
import concurrent.futures
import argparse
import json
import re
import sys
import shutil

def get_novel_info(url):
    """Scrapes the novel's main page to get metadata."""
    # Use stderr for logs, stdout for progress/results
    print("Fetching novel information...", flush=True, file=sys.stderr)
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching novel page {url}: {e}", flush=True, file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        title_element = soup.find('h1', class_='novel-title')
        if not title_element:
            print("Error: Could not find title element.", flush=True, file=sys.stderr)
            return None
        title = title_element.text.strip()

        author_div = soup.find('div', class_='author')
        if not author_div:
            print("Error: Could not find author div.", flush=True, file=sys.stderr)
            return None
        author = author_div.text.replace('Author:', '').strip()

        cover_url = None
        cover_element = soup.find('div', class_='fixed-img')
        if cover_element:
            img_tag = cover_element.find('img')
            if img_tag:
                # Prioritize data-src for lazy-loaded images, fall back to src
                if 'data-src' in img_tag.attrs and img_tag['data-src'].startswith('http'):
                    cover_url = img_tag['data-src']
                elif 'src' in img_tag.attrs and img_tag['src'].startswith('http'):
                    cover_url = img_tag['src']

        if not cover_url:
            print("Warning: Could not find a valid cover image URL.", flush=True, file=sys.stderr)

        total_chapters = None
        stats_div = soup.find('div', class_='header-stats')
        if stats_div:
            chapter_span = stats_div.find('span')
            if chapter_span:
                chapter_strong = chapter_span.find('strong')
                if chapter_strong:
                    match = re.search(r'(\d+)', chapter_strong.text)
                    if match:
                        total_chapters = int(match.group(1))

        if not total_chapters:
            latest_chapter_element = soup.find('li', class_='chapter-item')
            if latest_chapter_element and latest_chapter_element.find('a'):
                latest_chapter_link = latest_chapter_element.find('a')['href']
                match = re.search(r'chapter-(\d+)', latest_chapter_link)
                if match:
                    total_chapters = int(match.group(1))

        if not total_chapters:
            print("Error: Could not determine total number of chapters.", flush=True, file=sys.stderr)
            return None

        info = {
            "title": title,
            "author": author,
            "cover_url": cover_url,
            "total_chapters": total_chapters,
            "base_chapter_url": f"{url}/chapter-{{}}"
        }
        print(f"Successfully scraped info for: {title}", flush=True, file=sys.stderr)
        return info
    except Exception as e:
        print(f"Failed to parse novel information: {e}", flush=True, file=sys.stderr)
        return None

def download_cover_image(url, save_path):
    """Downloads an image from a URL and saves it."""
    if os.path.exists(save_path):
        print(f"Cover image already exists at {save_path}.", flush=True, file=sys.stderr)
        return save_path
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Cover downloaded and saved as {save_path}", flush=True, file=sys.stderr)
        return save_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading cover: {e}", flush=True, file=sys.stderr)
        return None

def get_chapter_html(chapter_url):
    """Fetches the HTML content of a given chapter URL."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        time.sleep(random.uniform(1, 3))
        response = requests.get(chapter_url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL {chapter_url}: {e}", flush=True, file=sys.stderr)
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    content_div = soup.find('div', id='content')
    if content_div:
        paragraphs = content_div.find_all('p')
        return "".join([str(p) for p in paragraphs])
    else:
        print(f"Could not find content div for URL: {chapter_url}", flush=True, file=sys.stderr)
        return None

def download_and_save_chapter(chapter_num, base_url, storage_path):
    """Fetches a single chapter and saves it to a file if it doesn't exist."""
    os.makedirs(storage_path, exist_ok=True)
    file_path = os.path.join(storage_path, f'chapter_{chapter_num}.html')
    
    if os.path.exists(file_path):
        # Don't print anything for skipped chapters to keep logs clean
        return file_path

    chapter_url = base_url.format(chapter_num)
    html_content = get_chapter_html(chapter_url)
    if html_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return file_path
    else:
        print(f"Failed to fetch chapter {chapter_num}. It will be skipped.", flush=True, file=sys.stderr)
        return None

def download_novel(base_url, start_chapter, end_chapter, storage_path, max_workers=10):
    """Downloads a range of chapters concurrently and saves them to disk."""
    chapters_to_fetch = range(start_chapter, end_chapter + 1)
    total_chapters_to_download = len(chapters_to_fetch)
    completed_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_chapter = {
            executor.submit(download_and_save_chapter, i, base_url, storage_path): i
            for i in chapters_to_fetch
        }
        
        for future in concurrent.futures.as_completed(future_to_chapter):
            completed_count += 1
            chapter_num = future_to_chapter[future]
            try:
                result = future.result()
                if result:
                    # Print progress to stdout for the parent process
                    print(f"PROGRESS:{completed_count}/{total_chapters_to_download}:Chapter {chapter_num} downloaded.", flush=True)
            except Exception as exc:
                print(f'Chapter {chapter_num} generated an exception: {exc}', flush=True, file=sys.stderr)

def get_ranked_list(sort_type='overall'):
    """Scrapes the ranking page based on sort type, downloads covers, and returns novel data."""
    base_url = "https://novelfire.net/ranking"
    sort_map = {
        'overall': base_url,
        'most-read': f"{base_url}/most-read",
        'most-review': f"{base_url}/most-review"
    }
    url = sort_map.get(sort_type, base_url)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    print(f"Fetching ranked list from {url}...", flush=True, file=sys.stderr)
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching ranking page: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    # The correct class for the list is 'rank-list'
    # The website structure has changed. The novels are now in 'ul.rank-novels'.
    rank_ul = soup.find('ul', class_='rank-novels')

    if not rank_ul:
        print("Could not find the ranking list element ('ul.rank-novels'). Dumping HTML for debugging.", file=sys.stderr)
        print("================ HTML DUMP ================", file=sys.stderr)
        print(soup.prettify(), file=sys.stderr)
        print("============== END HTML DUMP ==============", file=sys.stderr)
        return []

    # Create a temporary directory for covers
    covers_dir = "ranking_covers"
    if os.path.exists(covers_dir):
        shutil.rmtree(covers_dir)
    os.makedirs(covers_dir)
    print(f"Created temporary directory for covers at: {covers_dir}", file=sys.stderr)

    novel_list = []
    for i, novel_item in enumerate(rank_ul.find_all('li', class_='novel-item', limit=10)):
        title_element = novel_item.find('h2', class_='title')
        cover_element = novel_item.find('div', class_='cover-wrap')

        if not title_element or not title_element.find('a') or not cover_element:
            print(f"Skipping a novel item due to missing elements.", file=sys.stderr)
            continue

        novel_url = title_element.find('a')['href']
        title = title_element.text.strip()
        # Author is no longer available on the ranking page, so we set it to N/A.
        author = 'N/A'
        
        # The cover URL is now in the 'data-src' of the img tag.
        img_tag = cover_element.find('img')
        cover_url = img_tag['data-src'] if img_tag and 'data-src' in img_tag.attrs else None
        
        local_cover_path = None
        if cover_url:
            try:
                # Download the cover
                cover_response = requests.get(cover_url, headers=headers, timeout=10)
                cover_response.raise_for_status()
                
                # Guess extension from content type
                content_type = cover_response.headers.get('Content-Type', '')
                if 'jpeg' in content_type or 'jpg' in content_type:
                    file_extension = '.jpg'
                elif 'png' in content_type:
                    file_extension = '.png'
                elif 'webp' in content_type:
                    file_extension = '.webp'
                else:
                    # Fallback to guessing from URL, or default to .jpg
                    url_ext = os.path.splitext(cover_url)[1]
                    file_extension = url_ext if url_ext in ['.jpg', '.jpeg', '.png', '.webp'] else '.jpg'
                
                local_cover_path = os.path.join(covers_dir, f"cover_{i}{file_extension}")
                with open(local_cover_path, 'wb') as f:
                    f.write(cover_response.content)
                print(f"Downloaded cover for '{title}' to {local_cover_path}", file=sys.stderr)
            except requests.RequestException as e:
                print(f"Error downloading cover for {title}: {e}", file=sys.stderr)
                local_cover_path = None # Ensure it's None if download fails

        novel_list.append({
            "title": title,
            "author": author,
            "url": novel_url,
            "local_cover_path": local_cover_path
        })
    
    # If the loop completes and we have no novels, something is wrong with the page structure.
    if not novel_list:
        print("Found the rank list, but it contains no novel items. Dumping HTML for debugging.", file=sys.stderr)
        print("================ HTML DUMP ================", file=sys.stderr)
        print(soup.prettify(), file=sys.stderr)
        print("============== END HTML DUMP ==============", file=sys.stderr)
        return []

    # Now, fetch the author for each novel by visiting its page
    print("Fetching author details for each novel...", file=sys.stderr)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_novel = {executor.submit(get_novel_info, novel['url']): novel for novel in novel_list}
        for future in concurrent.futures.as_completed(future_to_novel):
            novel_data = future_to_novel[future]
            try:
                info = future.result()
                if info and info.get('author'):
                    novel_data['author'] = info['author']
                else:
                    # Keep it as N/A if info couldn't be fetched
                    novel_data['author'] = 'N/A'
            except Exception as exc:
                print(f"Exception fetching author for {novel_data['title']}: {exc}", file=sys.stderr)
                novel_data['author'] = 'N/A'

    return novel_list

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape a novel from novelfire.net.")
    parser.add_argument('--url', type=str, help="The main URL of the novel.")
    parser.add_argument('--start', type=int, default=1, help="The chapter number to start downloading from.")
    parser.add_argument('--end', type=int, help="The chapter number to end downloading at (optional).")
    parser.add_argument('--num-chapters', type=int, help="The number of chapters to download (optional).")
    parser.add_argument('--info-only', action='store_true', help="Only fetch and print novel info as JSON, then exit.")
    # Allow --browse to take an optional argument for the sort type
    parser.add_argument('--browse', nargs='?', const='overall', default=None,
                        help="Fetch and print the ranked list of novels as JSON. Optionally specify sort type: 'overall', 'most-read', 'most-review'.")
    args = parser.parse_args()

    # If --browse is passed, get the list, print as JSON, and exit.
    if args.browse is not None:
        sort_type = args.browse
        ranked_list = get_ranked_list(sort_type)
        if not ranked_list:
            # The get_ranked_list function will print debug info on failure.
            # We exit with an error code so the bot knows something went wrong.
            print(f"get_ranked_list(sort_type='{sort_type}') returned no novels. Exiting with error.", file=sys.stderr)
            exit(1)
        print(json.dumps(ranked_list))
        exit(0)

    # The rest of the script requires a URL
    if not args.url:
        print("Error: --url is required for this operation.", file=sys.stderr)
        exit(1)

    # If --info-only is passed, just get the info, print as JSON, and exit.
    if args.info_only:
        novel_info = get_novel_info(args.url)
        if not novel_info:
            exit(1)
        print(json.dumps(novel_info))
        exit(0)

    # --- Full download process ---
    novel_info = get_novel_info(args.url)
    if not novel_info:
        exit(1)

    novel_dir = novel_info['title']
    os.makedirs(novel_dir, exist_ok=True)

    # Save metadata
    metadata_path = os.path.join(novel_dir, 'metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(novel_info, f, indent=4)
    print(f"Metadata saved to {metadata_path}", flush=True, file=sys.stderr)

    # Determine chapter range
    start_chapter = args.start
    if args.end is not None:
        end_chapter = args.end
    elif args.num_chapters is not None:
        end_chapter = start_chapter + args.num_chapters - 1
    else:
        # If neither end nor num-chapters is specified, download all chapters
        end_chapter = novel_info['total_chapters']
    
    end_chapter = min(end_chapter, novel_info['total_chapters'])

    print(f"Starting download for '{novel_info['title']}' from chapter {start_chapter} to {end_chapter}.", flush=True, file=sys.stderr)
    chapters_dir = os.path.join(novel_dir, "chapters")
    download_novel(novel_info['base_chapter_url'], start_chapter, end_chapter, chapters_dir)

    if novel_info['cover_url']:
        print("Downloading cover image...", flush=True, file=sys.stderr)
        cover_path = os.path.join(novel_dir, "cover.jpg")
        download_cover_image(novel_info['cover_url'], cover_path)
    
    print("Download process finished.", flush=True, file=sys.stderr)
    # Print the final directory path to stdout for the orchestrator script
    print(f"NOVEL_DIR:{novel_dir}", flush=True)