from telegram.helpers import escape_markdown

class MarkdownUtils:
    @staticmethod
    def escape_text(text: str) -> str:
        return escape_markdown(text, version=2)