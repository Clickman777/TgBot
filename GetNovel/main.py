import subprocess
import sys
import argparse
import os

def run_scraper(url, start_chapter=None, end_chapter=None):
    """
    Runs the novel_scraper.py script, passing its progress up and capturing the final directory.
    """
    print("--- Starting Novel Scraper ---", file=sys.stderr, flush=True)
    command = [sys.executable, 'GetNovel/novel_scraper.py', '--url', url]
    if start_chapter:
        command.extend(['--start', str(start_chapter)])
    if end_chapter:
        command.extend(['--end', str(end_chapter)])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    novel_dir = None
    # Read stdout line by line to show progress and capture the final directory
    if process.stdout:
        for line in iter(process.stdout.readline, ''):
            stripped_line = line.strip()
            if stripped_line.startswith("PROGRESS:"):
                # Pass progress messages directly to this script's stdout
                print(line, end='', flush=True)
            elif stripped_line.startswith("NOVEL_DIR:"):
                novel_dir = stripped_line.split(":", 1)[1].strip()
        process.stdout.close()

    return_code = process.wait()

    if return_code != 0:
        print("\n--- Scraper failed ---", file=sys.stderr, flush=True)
        if process.stderr:
            stderr = process.stderr.read()
            print(stderr, file=sys.stderr, flush=True)
            process.stderr.close()
        return None
    
    print("\n--- Scraper finished successfully ---", file=sys.stderr, flush=True)
    return novel_dir

def run_epub_generator(input_dir):
    """
    Runs the epub_generator.py script and returns the path to the generated EPUB.
    """
    print("\n--- Starting EPUB Generator ---", file=sys.stderr, flush=True)
    result = subprocess.run(
        [sys.executable, 'GetNovel/epub_generator.py', '--input-dir', input_dir],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("--- EPUB Generator failed ---", file=sys.stderr, flush=True)
        print(result.stderr, file=sys.stderr, flush=True)
        return None
    
    # The epub_generator script prints the path of the created file.
    # We need to capture that from its stdout.
    # The generator now prints only the absolute path of the EPUB to stdout
    epub_path = result.stdout.strip()

    if epub_path and os.path.exists(epub_path):
        print("--- EPUB Generator finished successfully ---", file=sys.stderr, flush=True)
        return epub_path
    else:
        print(f"--- EPUB path not found or invalid: {epub_path} ---", file=sys.stderr, flush=True)
        return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrate novel scraping and EPUB generation.")
    parser.add_argument('--url', type=str, required=True, help="The main URL of the novel.")
    parser.add_argument('--start', type=int, help="The chapter number to start downloading from.")
    parser.add_argument('--end', type=int, help="The chapter number to end downloading at.")
    args = parser.parse_args()

    # Step 1: Run the scraper
    scraped_novel_dir = run_scraper(args.url, args.start, args.end)

    # Step 2: If scraper was successful, run the EPUB generator
    if scraped_novel_dir:
        epub_file_path = run_epub_generator(scraped_novel_dir)
        if epub_file_path:
            # Print the final epub path for the bot to capture
            print(f"EPUB_PATH:{epub_file_path}")
        else:
            print("\nCould not proceed to EPUB generation because the scraper failed to return a path.", file=sys.stderr, flush=True)
    else:
        print("\nCould not proceed to EPUB generation because the scraper failed.", file=sys.stderr, flush=True)