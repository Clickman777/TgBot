import argparse
from .manager import NovelManager

def main():
    parser = argparse.ArgumentParser(description="Download novels from the web.")
    parser.add_argument("-u", "--url", required=True, help="URL of the novel to download.")
    parser.add_argument("-s", "--start_chapter", type=int, default=1, help="The starting chapter number.")
    parser.add_argument("-e", "--end_chapter", type=int, help="The ending chapter number.")
    parser.add_argument("--update", action="store_true", help="Update an existing novel with the latest chapters.")
    
    args = parser.parse_args()
    
    manager = NovelManager()
    
    if args.update:
        manager.update_novel(args.url)
    else:
        manager.process_novel(args.url, args.start_chapter, args.end_chapter)

if __name__ == "__main__":
    main()