import os
import argparse
import sys
from ebooklib import epub
import json
import re

def create_epub_from_folder(input_dir):
    """
    Creates an EPUB file from a directory containing chapter files and metadata.
    """
    # Load metadata
    metadata_path = os.path.join(input_dir, 'metadata.json')
    if not os.path.exists(metadata_path):
        print(f"metadata.json not found in {input_dir}. Cannot build EPUB.", file=sys.stderr)
        return

    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    book_title = metadata.get('title', 'Unknown Title')
    author = metadata.get('author', 'Unknown Author')
    
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier(f'urn:uuid:{book_title.replace(" ", "-")}')
    book.set_title(book_title)
    book.set_language('en')
    book.add_author(author)

    # Set cover image
    cover_path = os.path.join(input_dir, "cover.jpg")
    if os.path.exists(cover_path):
        with open(cover_path, 'rb') as f:
            cover_image = f.read()
        book.set_cover("cover.jpg", cover_image)
    else:
        print("No cover image found.", file=sys.stderr)

    # Find and sort chapter files
    chapters_dir = os.path.join(input_dir, "chapters")
    if not os.path.isdir(chapters_dir):
        print(f"Chapters directory not found at {chapters_dir}", file=sys.stderr)
        return

    chapter_files = [f for f in os.listdir(chapters_dir) if f.endswith('.html')]
    def get_chapter_number(filename):
        match = re.search(r'(\d+)', filename)
        return int(match.group(1)) if match else 0

    chapter_files.sort(key=get_chapter_number)

    epub_chapters = []
    for chapter_file in chapter_files:
        chapter_num_match = re.search(r'(\d+)', chapter_file)
        if not chapter_num_match:
            continue
        
        chapter_num = chapter_num_match.group(1)
        chapter_title = f"Chapter {chapter_num}"
        file_path = os.path.join(chapters_dir, chapter_file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        epub_chapter = epub.EpubHtml(title=chapter_title, file_name=f'chapter_{chapter_num}.xhtml', lang='en')
        epub_chapter.content = f'<h1>{chapter_title}</h1>{html_content}'
        book.add_item(epub_chapter)
        epub_chapters.append(epub_chapter)

    if not epub_chapters:
        print("No chapter files found to add to the EPUB.", file=sys.stderr)
        return

    # Define TOC and Spine
    book.toc = epub_chapters
    book.spine = ['cover', 'nav'] + epub_chapters

    # Add default NCX and Nav file
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write the EPUB file
    output_filename = f"{book_title}.epub"
    output_path = os.path.join(input_dir, output_filename)
    epub.write_epub(output_path, book, {})
    print(f"Successfully created EPUB with {len(epub_chapters)} chapters.", file=sys.stderr)
    # Print the absolute path to stdout for the parent process
    print(os.path.abspath(output_path))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create an EPUB from a folder of downloaded novel chapters.")
    parser.add_argument('--input-dir', type=str, required=True, help="The directory where novel files are stored.")
    args = parser.parse_args()

    create_epub_from_folder(args.input_dir)