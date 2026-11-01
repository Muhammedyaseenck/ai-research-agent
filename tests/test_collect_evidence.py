import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parent.parent))

from main import collect_evidence


def step(tool, observation):
    # A stand-in for LangChain's (action, observation) pair
    return (SimpleNamespace(tool=tool), observation)


def test_no_steps_means_no_tools_and_no_sources():
    assert collect_evidence([]) == ([], [])


def test_urls_are_extracted_from_tool_output():
    obs = "Title: A\nURL: https://example.com/a\nSnippet: x"
    tools, sources = collect_evidence([step("search", obs)])
    assert tools == ["search"]
    assert sources == ["https://example.com/a"]


def test_duplicate_tools_and_urls_are_removed():
    obs = "URL: https://example.com/a"
    tools, sources = collect_evidence([step("search", obs), step("search", obs)])
    assert tools == ["search"]
    assert sources == ["https://example.com/a"]


def test_urls_mentioned_in_prose_are_not_sources():
    obs = "Info: see https://fake.example.com for details"
    _, sources = collect_evidence([step("wikipedia", obs)])
    assert sources == []


def test_sources_is_a_flat_list_of_strings():
    obs = "URL: https://example.com/a\n\nURL: https://example.com/b"
    _, sources = collect_evidence([step("search", obs)])
    assert sources == ["https://example.com/a", "https://example.com/b"]
    assert all(isinstance(s, str) for s in sources)