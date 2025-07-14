import os
import asyncio
import json
import shutil
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
from GetNovel.novel_list_manager import NovelListManager


# --- Setup ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")

OWNER_ID = 311524051  # !!! REPLACE WITH YOUR TELEGRAM USER ID !!!

# --- State Constants ---
STATE_IDLE = 0
STATE_AWAITING_URL = 1
STATE_AWAITING_CHAPTERS = 2
STATE_AWAITING_LIBRARY_CHAPTERS = 3

# --- State Management ---
def get_state(context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data:
        return context.user_data.get('state', STATE_IDLE)
    return STATE_IDLE

def set_state(context: ContextTypes.DEFAULT_TYPE, state: int):
    if context.user_data:
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
            "author": novel_info.author, "cover_url": novel_info.cover_url,
            "genres": novel_info.genres, "description": novel_info.description
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
        
        # This signals the application to stop the polling loop.
        context.application.stop_running()
    elif update.message:
        await update.message.reply_text("You are not authorized to use this command.")

async def getnovel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Please send me the URL of the novel's main page.")
    set_state(context, STATE_AWAITING_URL)

async def browse_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🏆 Overall", callback_data="browse_sort:overall")],
        [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
        [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
    ]
    if update.message:
        await update.message.reply_text("How would you like to sort the novels?", reply_markup=InlineKeyboardMarkup(keyboard))

def _generate_browse_markup():
    keyboard = [
        [InlineKeyboardButton("🏆 Overall", callback_data="browse_sort:overall")],
        [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
        [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
    ]
    return InlineKeyboardMarkup(keyboard)

def _generate_library_markup(user_library):
    text = "Here are your saved novels:\n\n"
    keyboard = []
    for i, novel in enumerate(user_library):
        safe_title = escape_markdown(novel.get('title', 'Unknown Title'), version=2)
        text += f"{i + 1}\\. *{safe_title}*\n"
        keyboard.append([
            InlineKeyboardButton("⬇️ Download", callback_data=f"lib_download:{i}"),
            InlineKeyboardButton("❌ Remove", callback_data=f"lib_remove:{i}")
        ])
    return text, InlineKeyboardMarkup(keyboard)

async def my_library_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not update.effective_user: return
    user_id = str(update.effective_user.id)
    user_library = load_libraries().get(user_id, [])
    if not user_library:
        await message.reply_text("Your library is empty.")
        return
    text, reply_markup = _generate_library_markup(user_library)
    await message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

# --- Message & Callback Handlers ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = get_state(context)
    if state == STATE_AWAITING_URL:
        await handle_url(update, context)
    elif state == STATE_AWAITING_CHAPTERS:
        await handle_chapters(update, context)
    elif state == STATE_AWAITING_LIBRARY_CHAPTERS:
        await handle_library_chapters(update, context)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    genres = ", ".join(novel_info.genres) if novel_info.genres else "N/A"
    description_text = novel_info.description or "No description available."
    keyboard = [[InlineKeyboardButton("📖 Add to Library", callback_data="library_add_current")]]
    if len(description_text) > 200:
        description = escape_markdown(description_text[:200] + "...", version=2)
        keyboard.append([InlineKeyboardButton("Full Summary", callback_data="read_more_getnovel")])
    else:
        description = escape_markdown(description_text, version=2)
    caption = f"*{safe_title}*\nby {safe_author}\n\nTotal Chapters: {novel_info.total_chapters or 'N/A'}\nGenres: {genres}\n\n{description}"
    reply_markup = InlineKeyboardMarkup(keyboard)
    if novel_info.cover_url:
        await message.reply_photo(photo=novel_info.cover_url, caption=caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
    else:
        await message.reply_text(caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
    await message.reply_text("What chapters do you want? (e.g., '1-50', 'all', or a single number)")
    set_state(context, STATE_AWAITING_CHAPTERS)

async def handle_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def handle_library_chapters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def browse_sort_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.message: return
    await query.answer()

    sort_type = query.data.split(':')[1]

    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="How would you like to sort the novels?",
        reply_markup=_generate_browse_markup()
    )

    scraper = Scraper()
    ranked_list = await asyncio.to_thread(scraper.get_ranked_list, sort_type)
    if not ranked_list:
        await query.message.edit_text(text="Failed to fetch the ranked list.")
        return

    context.user_data['browse_list'] = ranked_list
    context.user_data['browse_index'] = 0
    await send_browse_card(context, chat_id=query.message.chat_id, user_id=query.from_user.id)

async def send_browse_card(context, chat_id, user_id):
    if not context.user_data: return
    browse_list = context.user_data.get('browse_list', [])
    index = context.user_data.get('browse_index', 0)

    if not browse_list or not (0 <= index < len(browse_list)):
        await context.bot.send_message(chat_id, "Could not fetch the ranked list.")
        return

    novel = browse_list[index]
    novel_list_manager = NovelListManager()
    
    # --- Build Caption ---
    title = escape_markdown(novel.title, version=2)
    author = escape_markdown(novel.author or "Unknown", version=2)
    total_chapters = escape_markdown(str(novel.total_chapters or "N/A"), version=2)
    genres = ", ".join(novel.genres) if novel.genres else "N/A"
    description_text = novel.description or "No description available."
    if len(description_text) > 200:
        description = escape_markdown(description_text[:200] + "...", version=2)
    else:
        description = escape_markdown(description_text, version=2)

    caption = f"📚 *{title}*\n"
    caption += f"✍️ *Author:* {author}\n"
    caption += f"📖 *Chapters:* {total_chapters}\n"
    caption += f"🎭 *Genres:* {genres}\n"
    
    user_library = load_libraries().get(str(user_id), [])
    is_in_library = any(n['url'] == novel.url for n in user_library)
    if is_in_library:
        caption += f"✅ *In Your Library*\n"

    caption += f"\\-\\-\\-\n"
    caption += f"_Description:_\n{description}\n"
    caption += f"\\-\\-\\-"

    last_downloaded = novel_list_manager.get_last_downloaded_chapter(novel.title)
    downloaded_count = novel_list_manager.get_downloaded_chapter_count(novel.title)
    if downloaded_count > 0 and novel.total_chapters:
        progress = (downloaded_count / novel.total_chapters) * 100
        progress_text = f"{downloaded_count}/{novel.total_chapters} downloaded ({progress:.0f}%)"
        caption += f"\n*Progress:* {escape_markdown(progress_text, version=2)}"

    # --- Build Keyboard ---
    keyboard = []
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="browse_prev"))
    if index < len(browse_list) - 1:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data="browse_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    action_buttons = [
        InlineKeyboardButton("📖 Read Novel", callback_data=f"read_novel:{index}")
    ]
    if not is_in_library:
        action_buttons.append(InlineKeyboardButton("➕ Add to Library", callback_data=f"library_add_browse:{index}"))
    keyboard.append(action_buttons)
    
    utility_buttons = []
    if len(novel.description or "") > 200:
        utility_buttons.append(InlineKeyboardButton("Full Summary", callback_data=f"read_more:{index}"))

    utility_buttons.append(InlineKeyboardButton("🔄 Change Sort", callback_data="change_sort"))
    if last_downloaded > 0 and novel.total_chapters and novel.total_chapters > last_downloaded:
         utility_buttons.append(InlineKeyboardButton("⬆️ Update", callback_data=f"update_novel:{index}"))
    keyboard.append(utility_buttons)

    reply_markup = InlineKeyboardMarkup(keyboard)

    # --- Send Message ---
    try:
        if novel.local_cover_path and os.path.exists(novel.local_cover_path):
            with open(novel.local_cover_path, 'rb') as photo_file:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            raise ValueError("No local cover path")
    except Exception:
        await context.bot.send_message(chat_id=chat_id, text=f"{caption}\n\n_\\(Cover image not available\\)_", reply_markup=reply_markup, parse_mode='MarkdownV2')

async def browse_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()
    
    action = query.data
    
    if not context.user_data: return
    index = context.user_data.get('browse_index', 0)
    browse_list = context.user_data.get('browse_list', [])
    
    if action == "browse_next":
        index += 1
    elif action == "browse_prev":
        index -= 1
        
    if 0 <= index < len(browse_list) and isinstance(query.message, Message):
        context.user_data['browse_index'] = index
        await send_browse_card(context, chat_id=query.message.chat_id, user_id=query.from_user.id)

async def read_more_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the full novel description in a new message with a back button."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()

    try:
        index = int(query.data.split(':')[1])
    except (ValueError, IndexError):
        return

    if not context.user_data:
        return

    browse_list = context.user_data.get('browse_list', [])
    if not (0 <= index < len(browse_list)):
        return

    novel = browse_list[index]
    description_text = novel.description or "No description available."

    text = f"Full description for *{escape_markdown(novel.title, version=2)}*:\n\n{escape_markdown(description_text, version=2)}"

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        text=text,
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

async def read_more_getnovel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not context.user_data: return
    await query.answer()

    novel_info = context.user_data.get('current_novel_info')
    if not novel_info or not novel_info.description: return

    text = f"Full description for *{escape_markdown(novel_info.title, version=2)}*:\n\n{escape_markdown(novel_info.description, version=2)}"

    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_card")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        text=text,
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

async def read_novel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()

    payload = query.data.split(':')[1]
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
        if isinstance(query.message, Message):
            await query.message.edit_text("Sorry, there was an error selecting that novel.")

async def update_novel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()
    
    payload = query.data.split(':')[1]
    if not context.user_data or not payload: return
    
    index = int(payload)
    browse_list = context.user_data.get('browse_list', [])
    if not (0 <= index < len(browse_list)):
        if isinstance(query.message, Message):
            await query.message.edit_text("Error: Could not find the novel to update.")
        return
    
    novel_to_update = browse_list[index]
    if isinstance(query.message, Message):
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"Updating *{escape_markdown(novel_to_update.title, version=2)}*\\.\\.\\.", parse_mode='MarkdownV2')

    manager = NovelManager()
    # Running update in the background
    asyncio.create_task(manager.update_novel(novel_to_update.url))
    
    # Optionally, you can send a confirmation or update the card again after some time
    if isinstance(query.message, Message):
        await context.bot.send_message(chat_id=query.message.chat_id, text="Update process started in the background. You will be notified upon completion.")

async def change_sort_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query: return
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🏆 Overall", callback_data="browse_sort:overall")],
        [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
        [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
    ]
    if isinstance(query.message, Message):
        await query.message.edit_caption(caption="How would you like to sort the novels?", reply_markup=InlineKeyboardMarkup(keyboard))

async def add_to_library_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()

    payload = query.data.split(':')[1] if ':' in query.data else None
    action = query.data.split(':')[0]

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

async def back_to_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes the full description message, effectively going "back"."""
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    await query.message.delete()

async def library_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data: return
    await query.answer()

    action_full, payload = query.data.split(':', 1)
    action = action_full.split('_', 1)[1]
    
    if not payload: return
    user_id = str(query.from_user.id)
    libraries = load_libraries()
    user_library = libraries.get(user_id, [])
    index = int(payload)

    if not (0 <= index < len(user_library)):
        if isinstance(query.message, Message):
            await query.message.edit_text("Sorry, that novel is no longer in your library.")
        return

    novel_data = user_library[index]
    if action == "download":
        context.user_data['url'] = novel_data.get('url')
        safe_title = escape_markdown(novel_data.get('title', 'Unknown'), version=2)
        if isinstance(query.message, Message):
            await query.message.edit_text(f"Selected *{safe_title}*\\.", parse_mode='MarkdownV2')
            await query.message.reply_text("What chapters do you want? (e.g., '1-50', 'all')")
        set_state(context, STATE_AWAITING_LIBRARY_CHAPTERS)
    elif action == "remove":
        removed_novel = user_library.pop(index)
        libraries[user_id] = user_library
        save_libraries(libraries)
        
        if not user_library:
            if isinstance(query.message, Message):
                await query.message.edit_text("Your library is now empty.", reply_markup=None)
        else:
            text, reply_markup = _generate_library_markup(user_library)
            if isinstance(query.message, Message):
                await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

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
    application.add_handler(CallbackQueryHandler(browse_sort_callback, pattern='^browse_sort:'))
    application.add_handler(CallbackQueryHandler(browse_navigation_callback, pattern='^browse_(next|prev)$'))
    application.add_handler(CallbackQueryHandler(read_novel_callback, pattern='^read_novel:'))
    application.add_handler(CallbackQueryHandler(read_more_callback, pattern='^read_more:'))
    application.add_handler(CallbackQueryHandler(read_more_getnovel_callback, pattern='^read_more_getnovel$'))
    application.add_handler(CallbackQueryHandler(update_novel_callback, pattern='^update_novel:'))
    application.add_handler(CallbackQueryHandler(change_sort_callback, pattern='^change_sort$'))
    application.add_handler(CallbackQueryHandler(add_to_library_callback, pattern='^library_add_'))
    application.add_handler(CallbackQueryHandler(library_action_callback, pattern='^lib_'))
    application.add_handler(CallbackQueryHandler(back_to_card_callback, pattern='^back_to_card$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.run_polling()

if __name__ == "__main__":
    main()