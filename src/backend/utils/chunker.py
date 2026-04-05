"""
utils/chunker.py
Splits raw text into token-bounded overlapping chunks using tiktoken.
"""
from __future__ import annotations

import tiktoken


def chunk_text(
    text: str,
    max_tokens: int = 400,
    overlap: int = 50,
) -> list[dict]:
    """
    Split text into overlapping chunks bounded by token count.

    Uses the cl100k_base encoding (GPT-4 / text-embedding-ada-002 compatible).

    Args:
        text:       Raw document text.
        max_tokens: Maximum number of tokens per chunk.
        overlap:    Number of tokens to overlap between consecutive chunks.

    Returns:
        List of dicts:
            {
                "content":     str   — the chunk text,
                "chunk_index": int   — zero-based index,
                "token_count": int   — actual token count of this chunk
            }

    Raises:
        ValueError: If max_tokens <= overlap.
    """
    if max_tokens <= overlap:
        raise ValueError(
            f"max_tokens ({max_tokens}) must be greater than overlap ({overlap})."
        )

    enc = tiktoken.get_encoding("cl100k_base")

    # Encode the entire text into tokens
    all_tokens: list[int] = enc.encode(text)

    if not all_tokens:
        return []

    stride = max_tokens - overlap
    chunks: list[dict] = []
    start = 0
    chunk_index = 0

    while start < len(all_tokens):
        end = min(start + max_tokens, len(all_tokens))
        token_slice = all_tokens[start:end]

        # Decode back to text
        chunk_text_decoded = enc.decode(token_slice)

        chunks.append(
            {
                "content": chunk_text_decoded,
                "chunk_index": chunk_index,
                "token_count": len(token_slice),
            }
        )

        chunk_index += 1

        if end == len(all_tokens):
            break  # Reached the end

        start += stride

    return chunks
