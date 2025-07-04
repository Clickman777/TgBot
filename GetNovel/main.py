import argparse
import sys
from manager import NovelManager

def main():
    """
    Command-line interface for the Novel Scraper library.
    """
    parser = argparse.ArgumentParser(description="Scrape a novel and generate an EPUB.")
    parser.add_argument('--url', type=str, required=True, help="The main URL of the novel.")
    parser.add_argument('--start', type=int, default=1, help="The chapter to start downloading from.")
    parser.add_argument('--end', type=int, help="The chapter to end downloading at (optional).")
    args = parser.parse_args()

    # Use the NovelManager to process the novel
    manager = NovelManager()
    epub_path = manager.process_novel(args.url, args.start, args.end)

    if epub_path:
        # Print the final EPUB path to stdout for other scripts to capture
        print(f"EPUB_PATH:{epub_path}")
        sys.exit(0)
    else:
        print("Failed to create the EPUB.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()