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
        cover_image_path = ""
        if novel.local_cover_path and os.path.exists(novel.local_cover_path):
            with open(novel.local_cover_path, 'rb') as f:
                cover_image = f.read()
            cover_image_filename = os.path.basename(novel.local_cover_path)
            book.set_cover(cover_image_filename, cover_image)
            cover_image_path = cover_image_filename

        # Create title page
        title_page = self._create_title_page(novel, cover_image_path)
        book.add_item(title_page)
        
        # Create and add chapters
        epub_chapters = []
        for chapter in sorted(novel.chapters, key=lambda c: c.number):
            epub_chapter = epub.EpubHtml(
                title=f"Chapter {chapter.number}: {chapter.title}",
                file_name=f'chapter_{chapter.number}.xhtml',
                lang='en'
            )
            # Styling for a clear division between chapter number and title
            style = """
            <style>
                .chapter-header { text-align: center; margin-bottom: 30px; border-bottom: 1px solid #eee; padding-bottom: 15px; }
                .chapter-number {
                    display: block;
                    font-size: 1.2em;
                    color: #888;
                    font-weight: bold;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }
                .chapter-title {
                    display: block;
                    font-size: 2.2em;
                    font-weight: bold;
                    color: #000;
                    margin-top: 5px;
                }
            </style>
            """
            
            # Create a structured header
            header_html = f"""
            <div class="chapter-header">
                <span class="chapter-number">Chapter {chapter.number}</span>
                <h1 class="chapter-title">{chapter.title}</h1>
            </div>
            """
            
            epub_chapter.content = f'{style}{header_html}{chapter.content}'
            book.add_item(epub_chapter)
            epub_chapters.append(epub_chapter)

        if not epub_chapters:
            print("No chapters were processed for the EPUB.")
            return None

        # Define TOC and Spine
        book.toc = epub_chapters
        book.spine = ['cover', title_page] + epub_chapters

        # Add default NCX and Nav file
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # Write the EPUB file
        # Sanitize title for use in a filename
        safe_title = novel.title
        output_filename = f"{safe_title}.epub"
        output_path = os.path.join(novel.novel_dir, output_filename)
        
        try:
            epub.write_epub(output_path, book, {})
            print(f"Successfully created EPUB: {output_path}")
            return output_path
        except Exception as e:
            print(f"Error writing EPUB file: {e}")
            return None

    def _create_title_page(self, novel: Novel, cover_image_path: str) -> epub.EpubHtml:
        """Creates the title page for the EPUB."""
        title_page = epub.EpubHtml(
            title='Title Page',
            file_name='title.xhtml',
            lang='en'
        )
        
        # Basic styling for centering content
        # Adaptive and responsive styling for the title page
        style = """
        <style>
            html {
                font-size: 16px; /* Base font size */
            }
            body {
                font-family: sans-serif;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                text-align: center;
                margin: 0;
                padding: 5%; /* Use percentage for padding */
                min-height: 90vh; /* Use min-height to ensure it fills the screen but can grow */
            }
            h1 {
                font-size: 2.5rem; /* Use rem for scalable font size */
                margin: 0.5rem 0;
                word-wrap: break-word; /* Ensure long titles wrap */
            }
            h2 {
                font-size: 1.5rem; /* Use rem for scalable font size */
                font-style: italic;
                font-weight: normal;
                margin: 0.5rem 0;
            }
            img {
                max-width: 80%; /* Use percentage for responsive width */
                height: auto;
                margin: 1rem 0;
                border: 1px solid #ddd;
                padding: 5px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            /* Responsive adjustments for smaller screens */
            @media (max-width: 600px) {
                html {
                    font-size: 14px; /* Adjust base font size for smaller screens */
                }
                h1 {
                    font-size: 2rem;
                }
                h2 {
                    font-size: 1.2rem;
                }
                img {
                    max-width: 90%;
                }
            }
        </style>
        """
        
        image_tag = f'<img src="{cover_image_path}" alt="Cover Image"/>' if cover_image_path else ''

        title_page.content = f"""
        <html>
        <head>
            <title>{novel.title}</title>
            {style}
        </head>
        <body>
            <h1>{novel.title}</h1>
            {image_tag}
            <h2>by {novel.author}</h2>
        </body>
        </html>
        """
        return title_page