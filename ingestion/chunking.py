
def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into chunks, preserving paragraphs where possible."""
    if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars")

    chunks: list[str] = []
    current = ""

    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue

        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""

            start = 0
            step = max_chars - overlap
            while start < len(para):
                chunks.append(para[start:start + max_chars])
                if start + max_chars >= len(para):
                    break
                start += step
            continue

        if current and len(current) + 2 + len(para) > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para

    if current:
        chunks.append(current)

    return chunks
