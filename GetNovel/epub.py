import os
import json
from ebooklib import epub
from typing import Optional
from .models import Novel, Chapter

class EpubGenerator:
    """Generates an EPUB file from a Novel object."""

    def create_epub(self, novel: Novel) -> Optional[str]:
        """
        Creates an EPUB file for the given novel.
        Returns the path to the created file, or None on failure.
        """
        if not novel.novel_dir or not novel.chapters:
            print("Novel directory or chapters not found. Cannot build EPUB.")
            return None

        book = epub.EpubBook()

        # Set metadata
        book.set_identifier(f'urn:uuid:{novel.title.replace(" ", "-")}')
        book.set_title(novel.title)
        book.set_language('en')
        book.add_author(novel.author)

        # Set cover image
        if novel.local_cover_path and os.path.exists(novel.local_cover_path):
            with open(novel.local_cover_path, 'rb') as f:
                cover_image = f.read()
            book.set_cover(os.path.basename(novel.local_cover_path), cover_image)
        
        # Create and add chapters
        epub_chapters = []
        for chapter in sorted(novel.chapters, key=lambda c: c.number):
            epub_chapter = epub.EpubHtml(
                title=chapter.title,
                file_name=f'chapter_{chapter.number}.xhtml',
                lang='en'
            )
            epub_chapter.content = f'<h1>{chapter.title}</h1>{chapter.content}'
            book.add_item(epub_chapter)
            epub_chapters.append(epub_chapter)

        if not epub_chapters:
            print("No chapters were processed for the EPUB.")
            return None

        # Define TOC and Spine
        book.toc = epub_chapters
        book.spine = ['cover', 'nav'] + epub_chapters

        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Write the EPUB file
        output_filename = f"{novel.title}.epub"
        output_path = os.path.join(novel.novel_dir, output_filename)
        
        try:
            epub.write_epub(output_path, book, {})
            print(f"Successfully created EPUB: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error writing EPUB file: {e}")
            return None