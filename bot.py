import os
import logging
import subprocess
import sys
import asyncio
import json
import shutil
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get the bot token from environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

# Define states for conversation
GET_URL, GET_START_CHAPTER, GET_END_CHAPTER = range(3)

# --- Library Data Management ---
USER_LIBRARIES_FILE = "user_libraries.json"

def load_libraries():
    """Loads the user libraries from the JSON file."""
    if not os.path.exists(USER_LIBRARIES_FILE):
        return {}
    try:
        with open(USER_LIBRARIES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_libraries(libraries):
    """Saves the user libraries to the JSON file."""
    with open(USER_LIBRARIES_FILE, 'w') as f:
        json.dump(libraries, f, indent=4)

def add_to_library(user_id, novel_info):
    """Adds a novel to a user's library, avoiding duplicates."""
    user_id = str(user_id)
    libraries = load_libraries()
    
    if user_id not in libraries:
        libraries[user_id] = []

    # Avoid adding duplicates
    if not any(n['url'] == novel_info['url'] for n in libraries[user_id]):
        libraries[user_id].append({
            "title": novel_info['title'],
            "url": novel_info['url'],
            "author": novel_info.get('author', 'N/A')
        })
        save_libraries(libraries)
        return True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    await update.message.reply_text(
        "Welcome to the Novel Scraper Bot!\n\n"
        "Click the 'Menu' button or use /help to see the available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    await update.message.reply_text(
        "Available Commands:\n"
        "/browse - Browse a list of ranked novels.\n"
        "/getnovel - Start an interactive process to download a novel.\n"
        "/cancel - Cancel the current operation."
    )

async def getnovel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the /getnovel conversation and asks for the novel URL."""
    await update.message.reply_text(
        "Let's download a novel! First, please send me the URL of the novel's main page."
    )
    return GET_URL

async def get_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the URL, fetches novel info, and asks for the starting chapter."""
    url = update.message.text
    if not url or not url.startswith('http'):
        await update.message.reply_text("That doesn't look like a valid URL. Please send a valid URL.")
        return GET_URL
    
    context.user_data['url'] = url
    
    await update.message.reply_text("Fetching novel details, please wait...")
    try:
        command = [sys.executable, 'GetNovel/novel_scraper.py', '--url', url, '--info-only']
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await process.communicate()

        if process.returncode != 0:
            stderr = stderr_bytes.decode().strip()
            await update.message.reply_text(f"Could not fetch details for this URL. Error:\n`{stderr}`\nPlease try another URL, or /cancel.")
            return GET_URL

        novel_info = json.loads(stdout_bytes)
        context.user_data['novel_info'] = novel_info

        title = novel_info.get('title', 'N/A')
        author = novel_info.get('author', 'N/A')
        total_chapters = novel_info.get('total_chapters', 'N/A')
        cover_url = novel_info.get('cover_url')

        caption = (
            f"**{title}**\n"
            f"by {author}\n\n"
            f"Total Chapters: {total_chapters}\n\n"
            "Is this the correct novel?"
        )
        
        # Store novel info for potential library add
        context.user_data['current_novel_info'] = novel_info

        keyboard = [[InlineKeyboardButton("📖 Add to Library", callback_data="library_add")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if cover_url:
            await update.message.reply_photo(photo=cover_url, caption=caption, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=reply_markup)

        await update.message.reply_text("What chapter should I start from? (Send a number, or 'all' to download everything)")
        return GET_START_CHAPTER

    except Exception as e:
        logger.error(f"Failed to fetch novel info: {e}")
        await update.message.reply_text("An unexpected error occurred while fetching novel details. Please try again.")
        return GET_URL

async def get_start_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the start chapter and asks for the end chapter."""
    text = update.message.text
    if text.lower() == 'all':
        context.user_data['start_chapter'] = None
        context.user_data['end_chapter'] = None
        await update.message.reply_text("Got it! I will download all chapters.")
        asyncio.create_task(run_scraper_and_send(update, context))
        return ConversationHandler.END

    try:
        start_chapter = int(text)
        context.user_data['start_chapter'] = start_chapter
        await update.message.reply_text(f"Starting from chapter {start_chapter}. What is the last chapter you want? (Send a number)")
        return GET_END_CHAPTER
    except ValueError:
        await update.message.reply_text("That's not a valid number. Please send a chapter number.")
        return GET_START_CHAPTER

async def get_end_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the end chapter and starts the scraping process."""
    try:
        end_chapter = int(update.message.text)
        if end_chapter < context.user_data['start_chapter']:
            await update.message.reply_text("The end chapter can't be smaller than the start chapter. Please enter a valid end chapter.")
            return GET_END_CHAPTER
            
        context.user_data['end_chapter'] = end_chapter
        await update.message.reply_text(f"Okay, I will download from chapter {context.user_data['start_chapter']} to {end_chapter}.")
        asyncio.create_task(run_scraper_and_send(update, context))
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("That's not a valid number. Please send a chapter number.")
        return GET_END_CHAPTER

async def run_scraper_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """The core logic to run the scraper subprocess and handle updates."""
    url = context.user_data.get('url')
    start_chapter = context.user_data.get('start_chapter')
    end_chapter = context.user_data.get('end_chapter')

    status_message = await update.message.reply_text("Request received. Starting the process...")

    try:
        command = [sys.executable, 'GetNovel/main.py', '--url', url]
        if start_chapter is not None and end_chapter is not None:
            command.extend(['--start', str(start_chapter), '--end', str(end_chapter)])

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        epub_path = None
        last_update_text = ""

        if process.stdout:
            async for line in process.stdout:
                decoded_line = line.decode().strip()
                if not decoded_line:
                    continue

                if decoded_line.startswith("PROGRESS:"):
                    progress_text = decoded_line.split(":", 1)[1].strip()
                    if progress_text != last_update_text:
                        try:
                            await status_message.edit_text(f"Scraping in progress...\n\n{progress_text}")
                            last_update_text = progress_text
                        except Exception as e:
                            if "Message is not modified" not in str(e):
                                logger.warning(f"Could not edit message: {e}")
                
                elif decoded_line.startswith("EPUB_PATH:"):
                    epub_path = decoded_line.split(":", 1)[1].strip()

        stderr_bytes = await process.stderr.read() if process.stderr else b''
        stderr = stderr_bytes.decode().strip()
        if stderr:
            logger.info(f"Script stderr:\n{stderr}")

        await process.wait()

        if process.returncode != 0:
            await status_message.edit_text(f"An error occurred:\n`{stderr}`")
            return

        if epub_path and os.path.exists(epub_path):
            await status_message.edit_text("EPUB generated successfully! Uploading now...")
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(epub_path, 'rb'))
            try:
                os.remove(epub_path)
                logger.info(f"Cleaned up {epub_path}")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
        else:
            await status_message.edit_text(f"Could not find the generated EPUB file. Details:\n`{stderr}`")

    except Exception as e:
        logger.error(f"A critical error occurred in run_scraper_and_send: {e}")
        await update.message.reply_text(f"A critical error occurred: {e}")

async def browse_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Asks the user for the ranking criteria."""
    keyboard = [
        [InlineKeyboardButton("🏆 Overall Ranking", callback_data="browse_sort:overall")],
        [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
        [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("How would you like to sort the novels?", reply_markup=reply_markup)

async def browse_sort_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the selection of a sorting criteria and fetches the list."""
    query = update.callback_query
    await query.answer()

    sort_type = query.data.split(":", 1)[1]
    
    placeholder_message = await query.edit_message_text(f"Fetching ranked list (sorted by {sort_type}), please wait...")

    try:
        command = [sys.executable, 'GetNovel/novel_scraper.py', '--browse', sort_type]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await process.communicate()

        if process.returncode != 0:
            stderr = stderr_bytes.decode().strip()
            error_log_path = "scraper_error.log"
            with open(error_log_path, "w") as f:
                f.write(stderr)
            
            await placeholder_message.delete()
            await query.message.reply_text(
                "The scraper failed to fetch the ranked list. Please see the attached log for details."
            )
            await query.message.reply_document(document=open(error_log_path, 'rb'))
            os.remove(error_log_path)
            return

        ranked_list = json.loads(stdout_bytes)
        context.user_data['browse_list'] = ranked_list
        context.user_data['browse_index'] = 0
        
        await send_browse_card(update, context, message_to_edit=placeholder_message)

    except Exception as e:
        logger.error(f"Failed to fetch ranked list: {e}")
        await placeholder_message.edit_text("An unexpected error occurred while fetching the ranked list.")

async def send_browse_card(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None, message_to_edit=None) -> None:
    """Sends or edits a message to display the current novel in the browse list."""
    browse_list = context.user_data.get('browse_list', [])
    index = context.user_data.get('browse_index', 0)

    # Determine the message to edit. If called from a callback, it's query.message.
    # If called from the start, it's the placeholder message we passed.
    if query:
        message_to_edit = query.message
    
    if not message_to_edit:
        logger.error("send_browse_card called without a message to edit.")
        return

    if not browse_list:
        await message_to_edit.edit_text("Could not fetch the ranked list. Please try again later.")
        return

    novel = browse_list[index]
    title = novel.get('title', 'N/A')
    author = novel.get('author', 'N/A')
    # Use the local path now, not a URL
    local_cover_path = novel.get('local_cover_path')
    novel_url = novel.get('url')

    # Escape any special characters in the title and author for Markdown
    # Escape any special characters in the title and author for MarkdownV2
    safe_title = escape_markdown(title, version=2)
    safe_author = escape_markdown(author, version=2)
    caption = f"*{safe_title}*\n_By {safe_author}_\n\nRank {index + 1} of {len(browse_list)}"

    # --- Keyboard ---
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"browse_prev:{index}"))
    if index < len(browse_list) - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"browse_next:{index}"))
    
    keyboard = [
        nav_buttons,
        [
            InlineKeyboardButton("✅ Select", callback_data=f"browse_select:{index}"),
            InlineKeyboardButton("📖 Add to Library", callback_data=f"library_add_browse:{index}")
        ]
    ]
    # Filter out empty lists of buttons
    keyboard = [row for row in keyboard if row]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Now, we use the local file path to send the photo
    if local_cover_path and os.path.exists(local_cover_path):
        try:
            with open(local_cover_path, 'rb') as photo_file:
                media = InputMediaPhoto(media=photo_file, caption=caption, parse_mode='MarkdownV2')
                await message_to_edit.edit_media(media=media, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to send local photo {local_cover_path}: {e}. Falling back to text.")
            # Fallback if sending the local photo fails for some reason
            text_fallback = f"{caption}\n\n_(Cover image failed to load)_"
            await message_to_edit.edit_text(text=text_fallback, reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        # This is the case where the cover couldn't be downloaded by the scraper
        logger.warning(f"No local cover found for '{title}'. Sending text-only card.")
        text_fallback = f"{caption}\n\n_(Cover image not available)_"
        await message_to_edit.edit_text(text=text_fallback, reply_markup=reply_markup, parse_mode='MarkdownV2')

def cleanup_browse_data(context: ContextTypes.DEFAULT_TYPE):
    """Removes browse list, index, and the covers directory."""
    context.user_data.pop('browse_list', None)
    context.user_data.pop('browse_index', None)
    
    covers_dir = "ranking_covers"
    if os.path.exists(covers_dir):
        try:
            shutil.rmtree(covers_dir)
            logger.info(f"Successfully cleaned up {covers_dir} directory.")
        except Exception as e:
            logger.error(f"Error cleaning up {covers_dir}: {e}")

async def add_to_library_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Add to Library' button tap."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Determine which novel to add
    if query.data.startswith("library_add_browse:"):
        index = int(query.data.split(":")[1])
        novel_info = context.user_data.get('browse_list', [])[index]
    else: # From /getnovel flow
        novel_info = context.user_data.get('current_novel_info')

    if not novel_info:
        await query.edit_message_text("Sorry, I lost track of the novel. Please try again.")
        return

    if add_to_library(user_id, novel_info):
        await query.message.reply_text(f"Added *{escape_markdown(novel_info['title'], version=2)}* to your library\\.", parse_mode='MarkdownV2')
    else:
        await query.message.reply_text(f"_*_*{escape_markdown(novel_info['title'], version=2)}*_*_ is already in your library\\.", parse_mode='MarkdownV2')


async def my_library_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the user's personal library of saved novels."""
    user_id = str(update.effective_user.id)
    message = update.message or update.callback_query.message
    libraries = load_libraries()
    user_library = libraries.get(user_id, [])

    if not user_library:
        await message.reply_text("Your library is empty. You can add novels using the 'Add to Library' button when browsing or getting a novel.")
        return

    text = "Here are your saved novels:\n\n"
    keyboard = []
    for i, novel in enumerate(user_library):
        safe_title = escape_markdown(novel['title'], version=2)
        text += f"{i + 1}\\. *{safe_title}*\n"
        keyboard.append([
            InlineKeyboardButton(f"⬇️ Download {i+1}", callback_data=f"lib_download:{i}"),
            InlineKeyboardButton(f"❌ Remove {i+1}", callback_data=f"lib_remove:{i}")
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

async def library_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handles actions from the library view (download or remove)."""
    query = update.callback_query
    await query.answer()

    action, payload = query.data.split(":", 1)
    index = int(payload)
    
    user_id = str(query.from_user.id)
    libraries = load_libraries()
    user_library = libraries.get(user_id, [])

    if not (0 <= index < len(user_library)):
        await query.edit_message_text("Sorry, that novel is no longer in your library.")
        return None

    novel_info = user_library[index]

    if action == "lib_download":
        # Transition to the getnovel flow, pre-filling the URL
        context.user_data['url'] = novel_info['url']
        await query.edit_message_text(f"Selected *{escape_markdown(novel_info['title'], version=2)}*\\.", parse_mode='MarkdownV2')
        await query.message.reply_text("What chapter should I start from? (Send a number, or 'all')")
        return GET_START_CHAPTER
    
    elif action == "lib_remove":
        removed_novel = libraries[user_id].pop(index)
        save_libraries(libraries)
        await query.edit_message_text(f"Removed *{escape_markdown(removed_novel['title'], version=2)}* from your library\\.", parse_mode='MarkdownV2')
        # Refresh the library view
        await my_library_command(update, context)
        return None


async def browse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Handles all button taps for the browse menu (next, prev, select)."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, payload = data.split(":", 1)

    current_index = context.user_data.get('browse_index', 0)

    if action == "browse_next":
        new_index = current_index + 1
    elif action == "browse_prev":
        new_index = current_index - 1
    else: # This handles 'browse_select'
        selected_index = int(payload)
        browse_list = context.user_data.get('browse_list', [])
        
        if 0 <= selected_index < len(browse_list):
            url = browse_list[selected_index].get('url')
            context.user_data['url'] = url
            
            cleanup_browse_data(context)
            
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                "Novel selected! What chapter should I start from? (Send a number, or 'all')"
            )
            return GET_START_CHAPTER
        else:
            await query.edit_message_text("Sorry, there was an error selecting that novel.")
            return None

    browse_list = context.user_data.get('browse_list', [])
    if 0 <= new_index < len(browse_list):
        context.user_data['browse_index'] = new_index
        await send_browse_card(update, context, query=query)
    
    return None

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation, cleaning up any browse data."""
    await update.message.reply_text("Operation cancelled.")
    cleanup_browse_data(context)
    return ConversationHandler.END

async def post_init(application: Application) -> None:
    """Set the bot's command menu after initialization."""
    commands = [
        BotCommand("browse", "Browse ranked novels"),
        BotCommand("getnovel", "Download a novel by URL"),
        BotCommand("my_library", "View your saved novels"),
        BotCommand("help", "Show help message"),
        BotCommand("cancel", "Cancel the current operation"),
    ]
    await application.bot.set_my_commands(commands)

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("getnovel", getnovel_start),
            CallbackQueryHandler(browse_callback, pattern=r'^browse_select:.*')
        ],
        states={
            GET_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_url)],
            GET_START_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_chapter)],
            GET_END_CHAPTER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_chapter)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("browse", browse_start))
    # Handlers for the new browse flow
    application.add_handler(CallbackQueryHandler(browse_sort_callback, pattern=r'^browse_sort:.*'))
    application.add_handler(CallbackQueryHandler(browse_callback, pattern=r'^browse_(next|prev):.*'))
    
    # Handler for adding to library
    application.add_handler(CallbackQueryHandler(add_to_library_callback, pattern=r'^library_add.*'))

    # Handlers for library management
    application.add_handler(CommandHandler("my_library", my_library_command))
    application.add_handler(CallbackQueryHandler(library_action_callback, pattern=r'^lib_(download|remove):.*'))

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == "__main__":
    main()