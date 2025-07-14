import asyncio
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes
from GetNovel.manager import NovelManager
from GetNovel.scraper import Scraper
from GetNovel.models import Novel
from state_manager import BotStateManager
from markup_generator import MarkupGenerator
from markdown_utils import MarkdownUtils
from library_manager import LibraryManager # Import LibraryManager

class DownloadHandlers:
    def __init__(self, state_manager: BotStateManager, markup_generator: MarkupGenerator, library_manager: LibraryManager):
        self.state_manager = state_manager
        self.markup_generator = markup_generator
        self.library_manager = library_manager

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        state = self.state_manager.get_state(context)
        if state == self.state_manager.STATE_AWAITING_URL:
            await self.handle_url(update, context)
        elif state == self.state_manager.STATE_AWAITING_CHAPTERS:
            await self.handle_chapters(update, context)
        elif state == self.state_manager.STATE_AWAITING_LIBRARY_CHAPTERS:
            await self.handle_chapters(update, context, from_library=True) # Use a single handle_chapters

    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        
        safe_title = MarkdownUtils.escape_text(novel_info.title)
        safe_author = MarkdownUtils.escape_text(novel_info.author or "Unknown")
        genres = ", ".join(novel_info.genres) if novel_info.genres else "N/A"
        description_text = novel_info.description or "No description available."
        
        keyboard = [[InlineKeyboardButton("📖 Add to Library", callback_data="library_add_current")]]
        if len(description_text) > 200:
            description = MarkdownUtils.escape_text(description_text[:200] + "...")
            keyboard.append([InlineKeyboardButton("Full Summary", callback_data="read_more_getnovel")])
        else:
            description = MarkdownUtils.escape_text(description_text)
        
        caption = f"*{safe_title}*\nby {safe_author}\n\nTotal Chapters: {novel_info.total_chapters or 'N/A'}\nGenres: {genres}\n\n{description}"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if novel_info.cover_url:
            await message.reply_photo(photo=novel_info.cover_url, caption=caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
        else:
            await message.reply_text(caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
        
        await message.reply_text("What chapters do you want? (e.g., '1-50', 'all', or a single number)")
        self.state_manager.set_state(context, self.state_manager.STATE_AWAITING_CHAPTERS)

    async def handle_chapters(self, update: Update, context: ContextTypes.DEFAULT_TYPE, from_library: bool = False) -> None:
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
        asyncio.create_task(self._run_manager_and_send(update, context))
        self.state_manager.set_state(context, self.state_manager.STATE_IDLE)

    async def _run_manager_and_send(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
                # Delete the EPUB file after sending
                os.remove(epub_path)
                # Also delete the directory where the novel was processed if it's empty or no longer needed
                novel_dir = os.path.dirname(epub_path)
                if os.path.exists(novel_dir) and not os.listdir(novel_dir):
                    os.rmdir(novel_dir)
            else:
                await status_message.edit_text("Could not find the generated EPUB file.")
        except Exception as e:
            await status_message.edit_text(f"A critical error occurred: {e}")

    async def read_novel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            # cleanup_browse_data(context) # This should be handled by CommandHandlers or a central cleanup
            await query.edit_message_reply_markup(reply_markup=None)
            safe_title = novel.title
            if isinstance(query.message, Message):
                await query.message.reply_text(
                    f"Novel selected: {safe_title}\n\nWhat chapters do you want? (e.g., '1-50', 'all', or a single number)"
                )
            self.state_manager.set_state(context, self.state_manager.STATE_AWAITING_CHAPTERS)
        else:
            if isinstance(query.message, Message):
                await query.message.edit_text("Sorry, there was an error selecting that novel.")

    async def update_novel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"Updating *{MarkdownUtils.escape_text(novel_to_update.title)}*\\.\\.\\.", parse_mode='MarkdownV2')

        manager = NovelManager()
        # Running update in the background
        asyncio.create_task(manager.update_novel(novel_to_update.url))
        
        # Optionally, you can send a confirmation or update the card again after some time
        if isinstance(query.message, Message):
            await context.bot.send_message(chat_id=query.message.chat_id, text="Update process started in the background. You will be notified upon completion.")

    async def read_more_getnovel_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not context.user_data: return
        await query.answer()

        novel_info = context.user_data.get('current_novel_info')
        if not novel_info or not novel_info.description: return

        text = f"Full description for *{MarkdownUtils.escape_text(novel_info.title)}*:\n\n{MarkdownUtils.escape_text(novel_info.description)}"

        reply_markup = self.markup_generator.generate_read_more_markup()

        await query.message.reply_text(
            text=text,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )