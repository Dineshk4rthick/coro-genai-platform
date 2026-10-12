from pathlib import Path

import pytest

from ingestion.chunking import chunk_markdown, chunk_text

DOC = """# Contoso Test Policy

**Policy ID:** TEST-001
**Policy owner:** Human Resources

## 1. Purpose and scope

This policy is a test.

## 2. Sick leave

Employees receive 10 working days of sick leave per year.

A medical certificate is required after two consecutive days.

## 3. Questions and exceptions

Ask Human Resources.
"""

DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "docs"


# ---- chunk_text (size-based) -------------------------------------------------

def test_chunk_text_short_text_is_one_chunk():
    assert chunk_text("Hello.\n\nWorld.") == ["Hello.\n\nWorld."]


def test_chunk_text_respects_max_size_and_is_deterministic():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(20))
    first = chunk_text(text, max_chars=500, overlap=50)
    assert len(first) > 1
    assert all(len(c) <= 500 for c in first)
    assert first == chunk_text(text, max_chars=500, overlap=50)


def test_chunk_text_oversized_paragraph_is_windowed():
    chunks = chunk_text("x" * 2500, max_chars=1000, overlap=100)
    assert len(chunks) == 3 and all(len(c) <= 1000 for c in chunks)


def test_chunk_text_empty_and_bad_overlap():
    assert chunk_text("  \n\n ") == []
    with pytest.raises(ValueError):
        chunk_text("abc", max_chars=10, overlap=10)


# ---- chunk_markdown (section-based) ------------------------------------------

def test_one_chunk_per_section_plus_details():
    chunks = chunk_markdown(DOC)
    assert len(chunks) == 4  # details + 3 sections
    assert "Document details" in chunks[0] and "TEST-001" in chunks[0]


def test_every_chunk_carries_title_and_heading():
    for chunk in chunk_markdown(DOC):
        assert chunk.startswith("Contoso Test Policy \u2014 ")


def test_sick_leave_facts_stay_in_their_own_chunk():
    sick = [c for c in chunk_markdown(DOC) if "2. Sick leave" in c]
    assert len(sick) == 1
    assert "10 working days" in sick[0] and "medical certificate" in sick[0]
    assert "Human Resources" not in sick[0].split("\n\n", 1)[1]


def test_long_section_is_split_but_keeps_header():
    long_doc = "# Big Policy\n\n## 1. Rules\n\n" + "\n\n".join(
        f"Rule {i}. " + "detail " * 80 for i in range(10)
    )
    chunks = chunk_markdown(long_doc, max_chars=800)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)
    assert all(c.startswith("Big Policy \u2014 1. Rules") for c in chunks)


def test_markdown_chunking_is_deterministic():
    assert chunk_markdown(DOC) == chunk_markdown(DOC)


def test_markdown_edge_cases():
    assert chunk_markdown("   \n ") == []
    no_headings = chunk_markdown("# Only Title\n\nJust some text.")
    assert no_headings and no_headings[0].startswith("Only Title")
    with pytest.raises(ValueError):
        chunk_markdown(DOC, max_chars=100)


def test_real_policy_documents_chunk_cleanly():
    files = sorted(DOCS_DIR.glob("*.md"))
    assert len(files) == 8
    for f in files:
        chunks = chunk_markdown(f.read_text(encoding="utf-8"))
        assert len(chunks) >= 6, f.name
        assert all(len(c) <= 1500 for c in chunks), f.name
        assert all("\u2014" in c.split("\n", 1)[0] for c in chunks), f.name
