import os
import logging
import asyncio
import json
import shutil
import threading
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from dotenv import load_dotenv
from typing import cast

from GetNovel.manager import NovelManager
from GetNovel.scraper import Scraper
from GetNovel.models import Novel

# --- Setup ---
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

OWNER_ID = 123456789  # !!! REPLACE WITH YOUR TELEGRAM USER ID !!!

# --- State Constants ---
STATE_IDLE = 0
STATE_AWAITING_URL = 1
STATE_AWAITING_CHAPTERS = 2

# --- State Management ---
def get_state(context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data:
        return context.user_data.get('state', STATE_IDLE)
    return STATE_IDLE

def set_state(context: ContextTypes.DEFAULT_TYPE, state: int):
    if context.user_data:
        logger.info(f"Setting state to {state}")
        context.user_data['state'] = state

# --- Library Data Management ---
USER_LIBRARIES_FILE = "user_libraries.json"

def load_libraries():
    if not os.path.exists(USER_LIBRARIES_FILE):
        return {}
    try:
        with open(USER_LIBRARIES_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_libraries(libraries):
    with open(USER_LIBRARIES_FILE, 'w') as f:
        json.dump(libraries, f, indent=4)

def add_to_library(user_id, novel_info: Novel):
    user_id = str(user_id)
    libraries = load_libraries()
    if user_id not in libraries:
        libraries[user_id] = []
    if not any(n['url'] == novel_info.url for n in libraries[user_id]):
        libraries[user_id].append({
            "title": novel_info.title, "url": novel_info.url,
            "author": novel_info.author, "cover_url": novel_info.cover_url
        })
        save_libraries(libraries)
        return True
    return False

# --- Helper Functions ---
def cleanup_browse_data(context: ContextTypes.DEFAULT_TYPE):
    if context.user_data:
        context.user_data.pop('browse_list', None)
        context.user_data.pop('browse_index', None)
    covers_dir = "ranking_covers"
    if os.path.exists(covers_dir):
        shutil.rmtree(covers_dir)
        logger.info(f"Cleaned up {covers_dir} directory.")

async def run_manager_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data or not update.effective_chat: return
    url = context.user_data.get('url')
    start = context.user_data.get('start_chapter')
    end = context.user_data.get('end_chapter')
    chat_id = update.effective_chat.id
    if not isinstance(url, str) or not isinstance(start, int):
        await context.bot.send_message(chat_id, "Error: Missing novel information. Please start over.")
        return
    status_message = await context.bot.send_message(chat_id, "Request received. Starting the process...")
    try:
        manager = NovelManager()
        epub_path = await asyncio.to_thread(manager.process_novel, url, start, end)
        if epub_path and os.path.exists(epub_path):
            await status_message.edit_text("EPUB generated successfully! Uploading now...")
            with open(epub_path, 'rb') as epub_file:
                await context.bot.send_document(chat_id, document=epub_file)
            # The novel directory is preserved after sending the EPUB.
        else:
            await status_message.edit_text("Could not find the generated EPUB file.")
    except Exception as e:
        logger.error(f"A critical error occurred: {e}", exc_info=True)
        await status_message.edit_text(f"A critical error occurred: {e}")

# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Welcome! Use /help to see commands.")
    set_state(context, STATE_IDLE)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Commands:\n/browse - Browse ranked novels\n/getnovel - Download a novel\n/my_library - View your library\n/cancel - Cancel operation\n/stop - Stop the bot (owner only)"
        )
    set_state(context, STATE_IDLE)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Operation cancelled.")
    cleanup_browse_data(context)
    set_state(context, STATE_IDLE)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stops the bot (owner only)."""
    if update.effective_user and update.effective_user.id == OWNER_ID:
        if update.message:
            await update.message.reply_text("Shutting down...")
        
        # Use a thread to stop the application to avoid RuntimeError
        threading.Thread(target=context.application.stop).start()
    elif update.message:
        await update.message.reply_text("You are not authorized to use this command.")

async def getnovel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Command /getnovel received.")
    if update.message:
        await update.message.reply_text("Please send me the URL of the novel's main page.")
    set_state(context, STATE_AWAITING_URL)

async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Command /browse received.")
    keyboard = [
        [InlineKeyboardButton("🏆 Overall", callback_data="browse_sort:overall")],
        [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
        [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
    ]
    if update.message:
        await update.message.reply_text("How would you like to sort the novels?", reply_markup=InlineKeyboardMarkup(keyboard))

async def my_library_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Command /my_library received.")
    message = update.message
    if not message or not update.effective_user: return
    user_id = str(update.effective_user.id)
    user_library = load_libraries().get(user_id, [])
    if not user_library:
        await message.reply_text("Your library is empty.")
        return
    text = "Here are your saved novels:\n\n"
    keyboard = []
    for i, novel in enumerate(user_library):
        safe_title = escape_markdown(novel.get('title', 'Unknown'), version=2)
        text += f"{i + 1}\\. *{safe_title}*\n"
        keyboard.append([
            InlineKeyboardButton("⬇️ Download", callback_data=f"lib_download:{i}"),
            InlineKeyboardButton("❌ Remove", callback_data=f"lib_remove:{i}")
        ])
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')

# --- Message & Callback Handlers ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(context)
    if state == STATE_AWAITING_URL:
        await handle_url(update, context)
    elif state == STATE_AWAITING_CHAPTERS:
        await handle_chapters(update, context)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Handling URL...")
    message = update.message
    if not message or not message.text or not context.user_data: return
    url = message.text
    if not url.startswith('http'):
        await message.reply_text("That doesn't look like a valid URL. Please try again.")
        return
    context.user_data['url'] = url
    await message.reply_text("Fetching novel details, please wait...")
    scraper = Scraper()
    novel_info = await asyncio.to_thread(scraper.get_novel_info, url)
    if not novel_info:
        await message.reply_text("Could not fetch details for this URL. Please try another URL, or /cancel.")
        return
    context.user_data['current_novel_info'] = novel_info
    safe_title = escape_markdown(novel_info.title, version=2)
    safe_author = escape_markdown(novel_info.author or "Unknown", version=2)
    caption = f"*{safe_title}*\nby {safe_author}\n\nTotal Chapters: {novel_info.total_chapters or 'N/A'}"
    keyboard = [[InlineKeyboardButton("📖 Add to Library", callback_data="library_add_current")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if novel_info.cover_url:
        await message.reply_photo(photo=novel_info.cover_url, caption=caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else:
        await message.reply_text(caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
    await message.reply_text("What chapters do you want? (e.g., '1-50', 'all', or a single number)")
    set_state(context, STATE_AWAITING_CHAPTERS)

async def handle_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Handling chapter selection...")
    message = update.message
    if not message or not message.text or not context.user_data: return
    text = message.text.lower()
    try:
        if text == 'all':
            start_chapter, end_chapter = 1, None
        elif '-' in text:
            start_str, end_str = text.split('-', 1)
            start_chapter, end_chapter = int(start_str), int(end_str)
        else:
            start_chapter = end_chapter = int(text)
    except (ValueError, TypeError):
        await message.reply_text("Invalid format. Please use 'all', a single number, or a range like '1-50'.")
        return
    context.user_data['start_chapter'] = start_chapter
    context.user_data['end_chapter'] = end_chapter
    chapter_range = f"{start_chapter}-{end_chapter or 'end'}"
    await message.reply_text(f"Okay, I will download chapters: {chapter_range}.")
    asyncio.create_task(run_manager_and_send(update, context))
    set_state(context, STATE_IDLE)

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    
    action, *payload = query.data.split(':')
    payload = payload[0] if payload else None
    logger.info(f"Handling callback: action='{action}', payload='{payload}'")

    if action == 'browse_sort':
        await browse_sort_callback(query, context, payload)
    elif action in ['browse_next', 'browse_prev']:
        await browse_navigation_callback(query, context, action)
    elif action == 'browse_select':
        await browse_select_callback(update, query, context, payload)
    elif action.startswith('library_add'):
        await add_to_library_callback(query, context, action, payload)
    elif action.startswith('lib_'):
        await library_action_callback(update, query, context, action, payload)

async def browse_sort_callback(query, context, sort_type):
    await query.answer()
    message = await query.edit_message_text(f"Fetching ranked list (sorted by {sort_type}), please wait...")
    if not isinstance(message, Message): return
    scraper = Scraper()
    ranked_list = await asyncio.to_thread(scraper.get_ranked_list, sort_type)
    if not ranked_list:
        await message.edit_text("Failed to fetch the ranked list.")
        return
    context.user_data['browse_list'] = ranked_list
    context.user_data['browse_index'] = 0
    await send_browse_card(context, message_to_edit=message)

async def send_browse_card(context, message_to_edit):
    if not context.user_data: return
    browse_list = context.user_data.get('browse_list', [])
    index = context.user_data.get('browse_index', 0)
    if not browse_list or not (0 <= index < len(browse_list)):
        await message_to_edit.edit_text("Could not fetch the ranked list.")
        return
    novel = browse_list[index]
    safe_title = escape_markdown(novel.title, version=2)
    safe_author = escape_markdown(novel.author or "Unknown", version=2)
    caption = f"*{safe_title}*\n_By {safe_author}_\n\nChapters: {novel.total_chapters or 'N/A'}\nRank {index + 1} of {len(browse_list)}"
    nav_buttons = []
    if index > 0: nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data="browse_prev"))
    if index < len(browse_list) - 1: nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="browse_next"))
    keyboard = [
        nav_buttons,
        [InlineKeyboardButton("✅ Select", callback_data=f"browse_select:{index}")],
        [InlineKeyboardButton("📖 Add to Library", callback_data=f"library_add_browse:{index}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if novel.local_cover_path and os.path.exists(novel.local_cover_path):
            with open(novel.local_cover_path, 'rb') as photo_file:
                media = InputMediaPhoto(media=photo_file, caption=caption, parse_mode='MarkdownV2')
                await message_to_edit.edit_media(media=media, reply_markup=reply_markup)
        else:
            raise ValueError("No local cover path")
    except Exception:
        await message_to_edit.edit_text(text=f"{caption}\n\n_\\(Cover image not available\\)_", reply_markup=reply_markup, parse_mode='MarkdownV2')

async def browse_navigation_callback(query, context, action):
    await query.answer()
    if not context.user_data: return
    index = context.user_data.get('browse_index', 0)
    browse_list = context.user_data.get('browse_list', [])
    if action == "browse_next": index += 1
    elif action == "browse_prev": index -= 1
    if 0 <= index < len(browse_list) and isinstance(query.message, Message):
        context.user_data['browse_index'] = index
        await send_browse_card(context, message_to_edit=query.message)

async def browse_select_callback(update, query, context, payload):
    await query.answer()
    if not context.user_data or not payload: return
    selected_index = int(payload)
    browse_list = context.user_data.get('browse_list', [])
    if 0 <= selected_index < len(browse_list):
        novel = browse_list[selected_index]
        context.user_data['url'] = novel.url
        cleanup_browse_data(context)
        await query.edit_message_reply_markup(reply_markup=None)
        safe_title = novel.title
        if isinstance(query.message, Message):
            await query.message.reply_text(
                f"Novel selected: {safe_title}\n\nWhat chapters do you want? (e.g., '1-50', 'all', or a single number)"
            )
        set_state(context, STATE_AWAITING_CHAPTERS)
    else:
        await query.edit_message_text("Sorry, there was an error selecting that novel.")

async def add_to_library_callback(query, context, action, payload):
    await query.answer()
    if not context.user_data: return
    user_id = query.from_user.id
    novel_info = None
    if action == "library_add_browse" and payload:
        index = int(payload)
        browse_list = context.user_data.get('browse_list', [])
        if 0 <= index < len(browse_list):
            novel_info = browse_list[index]
    elif action == "library_add_current":
        novel_info = context.user_data.get('current_novel_info')
    if not isinstance(novel_info, Novel):
        if isinstance(query.message, Message):
            await query.message.reply_text("Sorry, I lost track of the novel.")
        return
    if add_to_library(user_id, novel_info):
        if isinstance(query.message, Message):
            await query.message.reply_text(f"Added *{escape_markdown(novel_info.title, version=2)}* to your library\\.", parse_mode='MarkdownV2')
    else:
        if isinstance(query.message, Message):
            await query.message.reply_text(f"_*{escape_markdown(novel_info.title, version=2)}*_ is already in your library\\.", parse_mode='MarkdownV2')

async def library_action_callback(update, query, context, action, payload):
    await query.answer()
    if not context.user_data or not payload: return
    user_id = str(query.from_user.id)
    libraries = load_libraries()
    user_library = libraries.get(user_id, [])
    index = int(payload)
    if not (0 <= index < len(user_library)):
        await query.edit_message_text("Sorry, that novel is no longer in your library.")
        return
    novel_data = user_library[index]
    if action == "lib_download":
        context.user_data['url'] = novel_data.get('url')
        safe_title = escape_markdown(novel_data.get('title', 'Unknown'), version=2)
        await query.edit_message_text(f"Selected *{safe_title}*\\.", parse_mode='MarkdownV2')
        if isinstance(query.message, Message):
            await query.message.reply_text("What chapters do you want? (e.g., '1-50', 'all')")
        set_state(context, STATE_AWAITING_CHAPTERS)
    elif action == "lib_remove":
        user_library.pop(index)
        save_libraries(libraries)
        if not user_library:
            await query.edit_message_text("Your library is now empty.")
        else:
            text = "Here are your saved novels:\n\n"
            keyboard = []
            for i, novel in enumerate(user_library):
                safe_title = escape_markdown(novel.get('title', 'Unknown Title'), version=2)
                text += f"{i + 1}\\. *{safe_title}*\n"
                keyboard.append([
                    InlineKeyboardButton("⬇️ Download", callback_data=f"lib_download:{i}"),
                    InlineKeyboardButton("❌ Remove", callback_data=f"lib_remove:{i}")
                ])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='MarkdownV2')

# --- Bot Setup ---
async def post_init(application: Application) -> None:
    commands = [
        BotCommand("browse", "Browse ranked novels"),
        BotCommand("getnovel", "Download a novel by URL"),
        BotCommand("my_library", "View your saved novels"),
        BotCommand("help", "Show help message"),
        BotCommand("cancel", "Cancel the current operation"),
        BotCommand("stop", "Stops the bot (owner only)"),
    ]
    await application.bot.set_my_commands(commands)

def main() -> None:
    application = Application.builder().token(cast(str, TOKEN)).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("getnovel", getnovel_command))
    application.add_handler(CommandHandler("browse", browse_command))
    application.add_handler(CommandHandler("my_library", my_library_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CallbackQueryHandler(handle_callbacks))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()