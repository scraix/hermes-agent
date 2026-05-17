"""CJK-aware search tokenization for Memory Graph.

Ported from Nocturne Memory's search_terms.py.
Uses jieba for Chinese/Japanese/Korean word segmentation.
"""

import re
from threading import Lock
from typing import Iterable, List

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False


class SearchTokenizer:
    """Tokenization with CJK segmentation support."""

    CJK_CHAR_CLASS = (
        "\u3400-\u4dbf"
        "\u4e00-\u9fff"
        "\uf900-\ufaff"
        "\u3040-\u30ff"
        "\u31f0-\u31ff"
        "\uac00-\ud7af"
    )

    CJK_RUN_RE = re.compile(f"[{CJK_CHAR_CLASS}]+")
    TOKEN_RE = re.compile(rf"[A-Za-z0-9_]+|[{CJK_CHAR_CLASS}]+")
    SEPARATOR_RE = re.compile(r"[:/.\\-]+")

    _jieba_lock = Lock()
    _registered_words: set = set()

    @staticmethod
    def dedupe(tokens: Iterable[str]) -> List[str]:
        """Remove duplicates while preserving order."""
        seen = set()
        ordered = []
        for token in tokens:
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered

    @classmethod
    def register_custom_words(cls, tokens: Iterable[str]) -> None:
        """Register custom words into jieba's dictionary."""
        if not _HAS_JIEBA:
            return
        with cls._jieba_lock:
            for token in tokens:
                if token in cls._registered_words or not cls.CJK_RUN_RE.fullmatch(token):
                    continue
                jieba.add_word(token)
                cls._registered_words.add(token)

    @classmethod
    def _segment_cjk(cls, text: str) -> List[str]:
        """Segment a CJK string into words using jieba."""
        if not _HAS_JIEBA:
            # Fallback: split into individual characters
            return [c for c in text if c.strip()]
        words = [word.strip() for word in jieba.cut_for_search(text) if word.strip()]
        return cls.dedupe(words or [text])

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        """Normalize and split text into tokens, applying CJK segmentation."""
        normalized = cls.SEPARATOR_RE.sub(" ", text).strip()
        if not normalized:
            return []

        tokens: List[str] = []
        for part in normalized.split():
            for token in cls.TOKEN_RE.findall(part):
                if cls.CJK_RUN_RE.fullmatch(token):
                    tokens.extend(cls._segment_cjk(token))
                else:
                    tokens.append(token.lower())
        return cls.dedupe(tokens)


def expand_query_terms(query: str) -> str:
    """Normalize query text into jieba-segmented tokens for search."""
    return " ".join(SearchTokenizer.tokenize(query))


def build_document_search_terms(
    path: str,
    uri: str,
    content: str,
    disclosure: str | None,
    glossary_text: str,
) -> str:
    """Build search terms with CJK segmentation for indexing."""
    glossary_tokens = [token for token in glossary_text.split() if token]
    SearchTokenizer.register_custom_words(glossary_tokens)

    tokens = list(glossary_tokens)
    for value in (path, uri, content, disclosure or "", glossary_text):
        tokens.extend(SearchTokenizer.tokenize(value))

    return " ".join(SearchTokenizer.dedupe(tokens))
