"""Split long answers to fit Telegram's 4096-character message limit."""

_TELEGRAM_MESSAGE_LIMIT = 4096
_SAFE_LIMIT = 3900  # headroom for formatting and future edits

_SEPARATORS = ["\n\n", "\n", ". ", " "]


def split_message(text: str, limit: int = _SAFE_LIMIT) -> list[str]:
    """Split text into chunks under `limit`, preferring paragraph breaks."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = -1
        for separator in _SEPARATORS:
            position = remaining.rfind(separator, 0, limit + 1)
            if position > 0:
                cut = position + len(separator)
                break
        if cut <= 0 or cut > limit:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
