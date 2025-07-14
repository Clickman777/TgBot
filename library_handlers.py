from telegram import Update, Message
from telegram.ext import ContextTypes
from state_manager import BotStateManager
from markup_generator import MarkupGenerator
from library_manager import LibraryManager
from markdown_utils import MarkdownUtils
from GetNovel.models import Novel # Import Novel for type checking

class LibraryHandlers:
    def __init__(self, state_manager: BotStateManager, markup_generator: MarkupGenerator, library_manager: LibraryManager):
        self.state_manager = state_manager
        self.markup_generator = markup_generator
        self.library_manager = library_manager

    async def my_library_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        if not message or not update.effective_user: return
        user_id = str(update.effective_user.id)
        user_library = self.library_manager.load_libraries().get(user_id, [])
        if not user_library:
            await message.reply_text("Your library is empty.")
            return
        text, reply_markup = self.markup_generator.generate_library_markup(user_library)
        await message.reply_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')

    async def add_to_library_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

        if not isinstance(novel_info, Novel): # Check if novel_info is None or not an instance of Novel
            if isinstance(query.message, Message):
                await query.message.reply_text("Sorry, I lost track of the novel.")
            return

        if self.library_manager.add_to_library(user_id, novel_info):
            if isinstance(query.message, Message):
                await query.message.reply_text(f"Added *{MarkdownUtils.escape_text(novel_info.title)}* to your library\\.", parse_mode='MarkdownV2')
        else:
            if isinstance(query.message, Message):
                await query.message.reply_text(f"_*{MarkdownUtils.escape_text(novel_info.title)}*_ is already in your library\\.", parse_mode='MarkdownV2')

    async def library_action_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data: return
        await query.answer()

        action_full, payload = query.data.split(':', 1)
        action = action_full.split('_', 1)[1]
        
        if not payload: return
        user_id = str(query.from_user.id)
        
        index = int(payload)

        if action == "download":
            user_library = self.library_manager.load_libraries().get(user_id, [])
            if not (0 <= index < len(user_library)):
                if isinstance(query.message, Message):
                    await query.message.edit_text("Sorry, that novel is no longer in your library.")
                return
            novel_data = user_library[index]
            context.user_data['url'] = novel_data.get('url')
            safe_title = MarkdownUtils.escape_text(novel_data.get('title', 'Unknown'))
            if isinstance(query.message, Message):
                await query.message.edit_text(f"Selected *{safe_title}*\\.", parse_mode='MarkdownV2')
                await query.message.reply_text("What chapters do you want? (e.g., '1-50', 'all')")
            self.state_manager.set_state(context, self.state_manager.STATE_AWAITING_LIBRARY_CHAPTERS)
        elif action == "remove":
            removed_novel = self.library_manager.remove_from_library(int(user_id), index)
            
            user_library = self.library_manager.load_libraries().get(user_id, []) # Reload library after removal
            if not user_library:
                if isinstance(query.message, Message):
                    await query.message.edit_text("Your library is now empty.", reply_markup=None)
            else:
                text, reply_markup = self.markup_generator.generate_library_markup(user_library)
                if isinstance(query.message, Message):
                    await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='MarkdownV2')