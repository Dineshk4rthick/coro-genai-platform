import re


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


_TITLE_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_SECTION_SPLIT_RE = re.compile(r"^##\s+", re.MULTILINE)


def chunk_markdown(text: str, max_chars: int = 1500) -> list[str]:
    """Split a Markdown policy into one chunk per '## ' section.

    Every chunk starts with '<document title> - <section heading>' so the
    passage still makes sense on its own, and so keyword and vector search can
    match on the topic. Sections longer than max_chars are split further with
    chunk_text(); each piece keeps the same header. Text before the first
    '## ' heading (policy ID, owner, effective date) becomes its own
    'Document details' chunk.
    """
    if max_chars < 300:
        raise ValueError("max_chars must be at least 300")

    text = text.strip()
    if not text:
        return []

    title_match = _TITLE_RE.search(text)
    title = title_match.group(1) if title_match else "Policy document"

    parts = _SECTION_SPLIT_RE.split(text)
    preamble, sections = parts[0], parts[1:]

    chunks: list[str] = []

    details = _TITLE_RE.sub("", preamble, count=1).strip()
    if details:
        chunks.append(f"{title} \u2014 Document details\n\n{details}")

    if not sections:
        # No '## ' headings: fall back to size-based chunking, keep the title.
        body = _TITLE_RE.sub("", preamble, count=1).strip() or preamble
        return [f"{title}\n\n{c}" for c in chunk_text(body, max_chars=max_chars - len(title) - 2)]

    for section in sections:
        heading, _, body = section.partition("\n")
        heading, body = heading.strip(), body.strip()
        if not body:
            continue
        header = f"{title} \u2014 {heading}"
        whole = f"{header}\n\n{body}"
        if len(whole) <= max_chars:
            chunks.append(whole)
            continue
        room = max(max_chars - len(header) - 2, 200)
        for piece in chunk_text(body, max_chars=room, overlap=min(100, room // 4)):
            chunks.append(f"{header}\n\n{piece}")

    return chunks
