import asyncio
import os
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from telegram.ext import ContextTypes
from GetNovel.scraper import Scraper
from GetNovel.novel_list_manager import NovelListManager
from GetNovel.models import Novel
from state_manager import BotStateManager
from markup_generator import MarkupGenerator
from markdown_utils import MarkdownUtils
from library_manager import LibraryManager

class BrowseHandlers:
    def __init__(self, state_manager: BotStateManager, markup_generator: MarkupGenerator, library_manager: LibraryManager):
        self.state_manager = state_manager
        self.markup_generator = markup_generator
        self.library_manager = library_manager

    async def browse_sort_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not query.message: return
        await query.answer()

        sort_type = query.data.split(':')[1]

        await query.message.delete() # Delete the "How would you like to sort the novels?" message

        scraper = Scraper()
        ranked_list = await asyncio.to_thread(scraper.get_ranked_list, sort_type)
        if not ranked_list:
            # If fetching fails, send a new message with the error
            await context.bot.send_message(chat_id=query.message.chat_id, text="Failed to fetch the ranked list.")
            return

        context.user_data['browse_list'] = ranked_list
        context.user_data['browse_index'] = 0
        # Send a new browse card after deleting the sorting message
        await self.send_browse_card(context, chat_id=query.message.chat_id, user_id=query.from_user.id)

    async def send_browse_card(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, message_to_edit: Message = None):
        if not context.user_data: return
        browse_list = context.user_data.get('browse_list', [])
        index = context.user_data.get('browse_index', 0)

        if not browse_list or not (0 <= index < len(browse_list)):
            if message_to_edit:
                await message_to_edit.edit_text("Could not fetch the ranked list.")
            else:
                await context.bot.send_message(chat_id, "Could not fetch the ranked list.")
            return

        novel = browse_list[index]
        novel_list_manager = NovelListManager()
        
        # --- Build Caption ---
        title = MarkdownUtils.escape_text(novel.title)
        author = MarkdownUtils.escape_text(novel.author or "Unknown")
        total_chapters = MarkdownUtils.escape_text(str(novel.total_chapters or "N/A"))
        genres = ", ".join(novel.genres) if novel.genres else "N/A"
        description_text = novel.description or "No description available."
        has_full_description = len(description_text) > 200
        description = MarkdownUtils.escape_text(description_text[:200] + "...") if has_full_description else MarkdownUtils.escape_text(description_text)

        caption = f"📚 *{title}*\n"
        caption += f"✍️ *Author:* {author}\n"
        caption += f"📖 *Chapters:* {total_chapters}\n"
        if novel.status: # Add status to caption
            status_text = "Completed" if novel.status.lower() == "completed" else "Ongoing"
            caption += f"📊 *Status:* {MarkdownUtils.escape_text(status_text)}\n"
        caption += f"🎭 *Genres:* {genres}\n"

        caption += f"\\-\\-\\-\n"
        caption += f"_Description:_\n{description}\n"
        caption += f"\\-\\-\\-"

        last_downloaded = novel_list_manager.get_last_downloaded_chapter(novel.title)
        downloaded_count = novel_list_manager.get_downloaded_chapter_count(novel.title)
        if downloaded_count > 0 and novel.total_chapters:
            progress = (downloaded_count / novel.total_chapters) * 100
            progress_text = f"{downloaded_count}/{novel.total_chapters} downloaded ({progress:.0f}%)"
            caption += f"\n\n*Progress:* {MarkdownUtils.escape_text(progress_text)}"

        user_library = self.library_manager.load_libraries().get(str(user_id), [])
        is_in_library = any(n['url'] == novel.url for n in user_library)
        if is_in_library:
            caption += f"\n✅ *In Your Library*"

        reply_markup = self.markup_generator.generate_browse_card_markup(
            index, len(browse_list), is_in_library, has_full_description, last_downloaded, novel.total_chapters
        )

        # --- Send/Edit Message ---
        try:
            if novel.local_cover_path and os.path.exists(novel.local_cover_path):
                if message_to_edit:
                    with open(novel.local_cover_path, 'rb') as photo_file:
                        await message_to_edit.edit_media(
                            media=InputMediaPhoto(media=photo_file, caption=caption, parse_mode='MarkdownV2'),
                            reply_markup=reply_markup
                        )
                else:
                    with open(novel.local_cover_path, 'rb') as photo_file:
                        await context.bot.send_photo(chat_id=chat_id, photo=photo_file, caption=caption, parse_mode='MarkdownV2', reply_markup=reply_markup)
            else:
                raise ValueError("No local cover path")
        except Exception:
            if message_to_edit:
                await message_to_edit.edit_text(text=f"{caption}\n\n_\\(Cover image not available\\)_", reply_markup=reply_markup, parse_mode='MarkdownV2')
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"{caption}\n\n_\\(Cover image not available\\)_", reply_markup=reply_markup, parse_mode='MarkdownV2')

    async def browse_navigation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            # Pass the existing message to edit
            await self.send_browse_card(context, chat_id=query.message.chat_id, user_id=query.from_user.id, message_to_edit=query.message)

    async def read_more_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

        text = f"Full description for *{MarkdownUtils.escape_text(novel.title)}*:\n\n{MarkdownUtils.escape_text(description_text)}"

        reply_markup = self.markup_generator.generate_read_more_markup()

        await query.message.reply_text(
            text=text,
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )

    async def change_sort_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query: return
        await query.answer()
        
        if isinstance(query.message, Message):
            # Edit the existing message to change sort options
            await query.message.edit_caption(caption="How would you like to sort the novels?", reply_markup=self.markup_generator.generate_browse_sort_markup())

    async def back_to_card_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Deletes the full description message, effectively going "back"."""
        query = update.callback_query
        if not query or not query.message:
            return
        await query.answer()
        # Re-send the browse card to replace the full description message
        await self.send_browse_card(context, chat_id=query.message.chat_id, user_id=query.from_user.id, message_to_edit=query.message)