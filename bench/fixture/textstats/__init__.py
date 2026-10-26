"""Small text statistics helpers."""


def word_count(text):
    """Return the number of words in text."""
    return len(text.split(" "))


def line_count(text):
    """Return the number of lines in text."""
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def average_word_length(text):
    """Return the mean length of the words in text, or 0.0 for no words."""
    words = text.split()
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)
