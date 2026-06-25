
import unittest
import sys
import os

# Import to add this so this file can import correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend/fission")))

from utils.clean_and_format_util import clean_text, clean_and_format
from utils.engagement_calc_util import engagement_calc


class TestUtils(unittest.TestCase):

    def test_engagement_calc(self):
        self.assertEqual(engagement_calc(1, 1, 1), 7)
        self.assertEqual(engagement_calc(0, 0, 0), 0)
        self.assertEqual(engagement_calc(5, 3, 2), 5*1 + 3*2 + 2*4)

    def test_clean_text(self):
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text("Hello @dfawd! Check out https://example.com #Bitcoin"), "hello check out bitcoin")
        self.assertEqual(clean_text("&lt;b&gt;Bold text&lt;/b&gt;"), "bold text")
        self.assertEqual(clean_text("huge     space"), "huge space")

    def test_clean_and_format(self):
        result = clean_and_format(
            "Test post @dfawd #Crypto",
            "2024-01-01",
            "bluesky",
            10,
            5,
            2
        )
        self.assertEqual(result["text"], "test post crypto")
        self.assertEqual(result["created_at"], "2024-01-01")
        self.assertEqual(result["source"], "bluesky")
        self.assertEqual(result["engagement"], 10*1 + 5*2 + 2*4)


if __name__ == "__main__":
    unittest.main()
