from telegram.ext import ContextTypes

class BotStateManager:
    STATE_IDLE = 0
    STATE_AWAITING_URL = 1
    STATE_AWAITING_CHAPTERS = 2
    STATE_AWAITING_LIBRARY_CHAPTERS = 3

    def get_state(self, context: ContextTypes.DEFAULT_TYPE) -> int:
        if context.user_data:
            return context.user_data.get('state', self.STATE_IDLE)
        return self.STATE_IDLE

    def set_state(self, context: ContextTypes.DEFAULT_TYPE, state: int):
        if context.user_data:
            context.user_data['state'] = state