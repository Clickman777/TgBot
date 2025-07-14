import os
from typing import cast
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from dotenv import load_dotenv

from state_manager import BotStateManager
from library_manager import LibraryManager
from markup_generator import MarkupGenerator
from command_handlers import CommandHandlers
from browse_handlers import BrowseHandlers
from download_handlers import DownloadHandlers
from library_handlers import LibraryHandlers

class TelegramBotApp:
    def __init__(self):
        load_dotenv()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")
        
        self.owner_id = 311524051 # !!! REPLACE WITH YOUR TELEGRAM USER ID !!!

        self.application = Application.builder().token(cast(str, self.token)).post_init(self._post_init).build()
        
        self.state_manager = BotStateManager()
        self.library_manager = LibraryManager()
        self.markup_generator = MarkupGenerator()
        
        self.command_handlers = CommandHandlers(self.state_manager, self.owner_id)
        self.browse_handlers = BrowseHandlers(self.state_manager, self.markup_generator, self.library_manager)
        self.download_handlers = DownloadHandlers(self.state_manager, self.markup_generator, self.library_manager)
        self.library_handlers = LibraryHandlers(self.state_manager, self.markup_generator, self.library_manager)
        
        self.add_handlers()

    async def _post_init(self, application: Application) -> None:
        commands = [
            BotCommand("browse", "Browse ranked novels"),
            BotCommand("getnovel", "Download a novel by URL"),
            BotCommand("my_library", "View your saved novels"),
            BotCommand("help", "Show help message"),
            BotCommand("cancel", "Cancel the current operation"),
            BotCommand("stop", "Stops the bot (owner only)"),
        ]
        await application.bot.set_my_commands(commands)

    def add_handlers(self):
        # Command Handlers
        self.application.add_handler(CommandHandler("start", self.command_handlers.start_command))
        self.application.add_handler(CommandHandler("help", self.command_handlers.help_command))
        self.application.add_handler(CommandHandler("cancel", self.command_handlers.cancel_command))
        self.application.add_handler(CommandHandler("getnovel", self.command_handlers.getnovel_command))
        self.application.add_handler(CommandHandler("browse", self.command_handlers.browse_command))
        self.application.add_handler(CommandHandler("my_library", self.library_handlers.my_library_command))
        self.application.add_handler(CommandHandler("stop", self.command_handlers.stop_command))

        # Callback Query Handlers
        self.application.add_handler(CallbackQueryHandler(self.browse_handlers.browse_sort_callback, pattern='^browse_sort:'))
        self.application.add_handler(CallbackQueryHandler(self.browse_handlers.browse_navigation_callback, pattern='^browse_(next|prev)$'))
        self.application.add_handler(CallbackQueryHandler(self.download_handlers.read_novel_callback, pattern='^read_novel:'))
        self.application.add_handler(CallbackQueryHandler(self.browse_handlers.read_more_callback, pattern='^read_more:'))
        self.application.add_handler(CallbackQueryHandler(self.download_handlers.read_more_getnovel_callback, pattern='^read_more_getnovel$'))
        self.application.add_handler(CallbackQueryHandler(self.download_handlers.update_novel_callback, pattern='^update_novel:'))
        self.application.add_handler(CallbackQueryHandler(self.browse_handlers.change_sort_callback, pattern='^change_sort$'))
        self.application.add_handler(CallbackQueryHandler(self.library_handlers.add_to_library_callback, pattern='^library_add_'))
        self.application.add_handler(CallbackQueryHandler(self.library_handlers.library_action_callback, pattern='^lib_'))
        self.application.add_handler(CallbackQueryHandler(self.browse_handlers.back_to_card_callback, pattern='^back_to_card$'))

        # Message Handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.download_handlers.handle_text))

    def run(self):
        self.application.run_polling()