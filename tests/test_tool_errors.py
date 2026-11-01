import requests

import tools


class FakeResponse:
    """A stand-in for a requests response, with only what tools.py uses."""

    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class FakeSearch:
    """A stand-in for the DuckDuckGo tool. Either returns results or raises."""

    def __init__(self, results=None, error=None):
        self._results = results
        self._error = error

    def invoke(self, query):
        if self._error:
            raise self._error
        return self._results


def search_data(titles):
    return {"query": {"search": [{"title": t} for t in titles]}}


def page_data(title):
    return {"query": {"pages": {"1": {"title": title, "extract": f"About {title}."}}}}


def has_url_line(text):
    return any(line.startswith("URL: ") for line in text.splitlines())


def test_wikipedia_search_timeout_returns_message(monkeypatch):
    def fake_get(*args, **kwargs):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(tools.requests, "get", fake_get)

    result = tools.search_wikipedia("anything")

    assert result.startswith("Wikipedia search failed")
    assert not has_url_line(result)


def test_one_failed_page_does_not_lose_the_others(monkeypatch):
    def fake_get(url, params=None, **kwargs):
        if "list" in params:  # the first call: the search itself
            return FakeResponse(search_data(["Alpha", "Beta", "Gamma"]))
        if params["titles"] == "Beta":  # one page fails
            raise requests.exceptions.Timeout()
        return FakeResponse(page_data(params["titles"]))

    monkeypatch.setattr(tools.requests, "get", fake_get)

    result = tools.search_wikipedia("anything")

    assert "Title: Alpha" in result
    assert "Title: Gamma" in result
    assert "Title: Beta" not in result


def test_all_pages_failing_returns_message(monkeypatch):
    def fake_get(url, params=None, **kwargs):
        if "list" in params:
            return FakeResponse(search_data(["Alpha", "Beta"]))
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(tools.requests, "get", fake_get)

    result = tools.search_wikipedia("anything")

    assert result == "Wikipedia pages could not be retrieved for this query."
    assert not has_url_line(result)


def test_web_search_failure_returns_message(monkeypatch):
    # Replace the whole `search` object in tools.py, not a method on it.
    monkeypatch.setattr(tools, "search", FakeSearch(error=RuntimeError("rate limited")))

    result = tools.search_web("anything")

    assert result.startswith("Web search failed")
    assert not has_url_line(result)


def test_web_search_with_no_results_returns_message(monkeypatch):
    monkeypatch.setattr(tools, "search", FakeSearch(results=[]))

    assert tools.search_web("anything") == "No web results found."