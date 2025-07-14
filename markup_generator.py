from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from typing import List, Dict, Any

class MarkupGenerator:
    def generate_browse_sort_markup(self) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("🏆 Overall", callback_data="browse_sort:overall")],
            [InlineKeyboardButton("🔥 Most Read", callback_data="browse_sort:most-read")],
            [InlineKeyboardButton("⭐ By Reviews", callback_data="browse_sort:most-review")],
            [InlineKeyboardButton("💬 By Comments", callback_data="browse_sort:most-comment")],
            [InlineKeyboardButton("❤️ By Collections", callback_data="browse_sort:most-favored")],
        ]
        return InlineKeyboardMarkup(keyboard)

    def generate_library_markup(self, user_library: List[Dict[str, Any]]) -> tuple[str, InlineKeyboardMarkup]:
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

    def generate_read_more_markup(self) -> InlineKeyboardMarkup:
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_card")]]
        return InlineKeyboardMarkup(keyboard)

    def generate_browse_card_markup(self, index: int, browse_list_len: int, is_in_library: bool, has_full_description: bool, last_downloaded: int, total_chapters: int) -> InlineKeyboardMarkup:
        keyboard = []
        nav_buttons = []
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data="browse_prev"))
        if index < browse_list_len - 1:
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
        if has_full_description:
            utility_buttons.append(InlineKeyboardButton("Full Summary", callback_data=f"read_more:{index}"))

        utility_buttons.append(InlineKeyboardButton("🔄 Change Sort", callback_data="change_sort"))
        if last_downloaded > 0 and total_chapters and total_chapters > last_downloaded:
             utility_buttons.append(InlineKeyboardButton("⬆️ Update", callback_data=f"update_novel:{index}"))
        keyboard.append(utility_buttons)

        return InlineKeyboardMarkup(keyboard)