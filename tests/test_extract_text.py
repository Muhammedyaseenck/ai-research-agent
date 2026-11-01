import sys
from pathlib import Path

# Let the tests import main.py from the project folder
sys.path.append(str(Path(__file__).resolve().parent.parent))

from main import extract_text


def test_plain_string_is_returned_unchanged():
    assert extract_text('{"a": 1}') == '{"a": 1}'


def test_markdown_fences_are_removed():
    raw = '```json\n{"a": 1}\n```'
    assert extract_text(raw) == '{"a": 1}'


def test_gemini_content_blocks_are_joined():
    raw = [{"type": "text", "text": '```json\n{"a": 1}\n```', "extras": {"signature": "xyz"}}]
    assert extract_text(raw) == '{"a": 1}'


def test_non_text_blocks_are_ignored():
    raw = [
        {"type": "thinking", "text": "ignore me"},
        {"type": "text", "text": '{"a": 1}'},
    ]
    assert extract_text(raw) == '{"a": 1}'