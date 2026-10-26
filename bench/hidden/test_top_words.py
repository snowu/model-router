import unittest

from textstats import top_words


class TestTopWords(unittest.TestCase):
    def test_counts_and_order(self):
        text = "the cat and the hat and the bat"
        self.assertEqual(top_words(text, 2), [("the", 3), ("and", 2)])

    def test_case_and_punctuation(self):
        text = "Hello, hello! HELLO? world."
        self.assertEqual(top_words(text, 2), [("hello", 3), ("world", 1)])

    def test_ties_alphabetical(self):
        self.assertEqual(top_words("b a c", 3), [("a", 1), ("b", 1), ("c", 1)])

    def test_n_larger_than_vocabulary(self):
        self.assertEqual(top_words("one two", 5), [("one", 1), ("two", 1)])

    def test_empty(self):
        self.assertEqual(top_words("", 3), [])


if __name__ == "__main__":
    unittest.main()
