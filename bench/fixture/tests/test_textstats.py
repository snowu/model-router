import unittest

from textstats import average_word_length, line_count, word_count


class TestTextstats(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("the quick brown fox"), 4)

    def test_line_count(self):
        self.assertEqual(line_count("a\nb\nc"), 3)
        self.assertEqual(line_count("a\nb\n"), 2)
        self.assertEqual(line_count(""), 0)

    def test_average_word_length(self):
        self.assertEqual(average_word_length("ab abcd"), 3.0)
        self.assertEqual(average_word_length(""), 0.0)


if __name__ == "__main__":
    unittest.main()
