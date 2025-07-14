import os
import shutil
from telegram import Update, Message
from telegram.ext import ContextTypes
from state_manager import BotStateManager
from markup_generator import MarkupGenerator

class CommandHandlers:
    def __init__(self, state_manager: BotStateManager, owner_id: int):
        self.state_manager = state_manager
        self.owner_id = owner_id
        self.markup_generator = MarkupGenerator() # Assuming MarkupGenerator is stateless

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Welcome! Use /help to see commands.")
        self.state_manager.set_state(context, self.state_manager.STATE_IDLE)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(
                "Commands:\n/browse - Browse ranked novels\n/getnovel - Download a novel\n/my_library - View your library\n/cancel - Cancel operation\n/stop - Stop the bot (owner only)"
            )
        self.state_manager.set_state(context, self.state_manager.STATE_IDLE)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Operation cancelled.")
        self._cleanup_browse_data(context)
        self.state_manager.set_state(context, self.state_manager.STATE_IDLE)

    def _cleanup_browse_data(self, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data:
            context.user_data.pop('browse_list', None)
            context.user_data.pop('browse_index', None)
        covers_dir = "ranking_covers"
        if os.path.exists(covers_dir):
            shutil.rmtree(covers_dir)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Stops the bot (owner only)."""
        if update.effective_user and update.effective_user.id == self.owner_id:
            if update.message:
                await update.message.reply_text("Shutting down...")
            context.application.stop_running()
        elif update.message:
            await update.message.reply_text("You are not authorized to use this command.")

    async def getnovel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("Please send me the URL of the novel's main page.")
        self.state_manager.set_state(context, self.state_manager.STATE_AWAITING_URL)

    async def browse_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text("How would you like to sort the novels?", reply_markup=self.markup_generator.generate_browse_sort_markup())