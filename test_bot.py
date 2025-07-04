import unittest
from unittest.mock import patch
from bot import main

class TestBot(unittest.TestCase):
    @patch('bot.Application.run_polling')
    def test_bot_starts(self, mock_run_polling):
        # This test will check if the bot's main function can be called without raising an exception.
        # It mocks the run_polling method to prevent the bot from actually starting.
        try:
            main()
        except Exception as e:
            self.fail(f"main() raised {e.__class__.__name__} unexpectedly!")

if __name__ == '__main__':
    unittest.main()