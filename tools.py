import requests

from langchain_community.tools import DuckDuckGoSearchResults
from langchain_core.tools import Tool


# 1. Initialize DuckDuckGo Search
search = DuckDuckGoSearchResults(output_format="list", max_results=4)


def search_web(query):
    try:
        results = search.invoke(query)
    except Exception as e:
        # Broad catch on purpose: the search library can fail in many ways.
        # Return text (not a crash) so the agent can read it and adapt.
        return (
            f"Web search failed ({type(e).__name__}). "
            "No web results are available for this query."
        )

    lines = []
    for r in results:
        lines.append(
            f"Title: {r.get('title')}\nURL: {r.get('link')}\nSnippet: {r.get('snippet')}"
        )
    return "\n\n".join(lines) if lines else "No web results found."


search_tool = Tool(
    name="search",
    func=search_web,
    description="Search the web for current information. Returns titles, URLs and snippets."
)


# 2. Wikipedia Search Function
def search_wikipedia(query):

    url = "https://en.wikipedia.org/w/api.php"

    headers = {
        "User-Agent": "AIResearchAgent/1.0 (educational project)"
    }

    # Search Wikipedia
    try:
        search_response = requests.get(
            url,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json"
            },
            headers=headers,
            timeout=20
        )

        search_response.raise_for_status()

        results = search_response.json()["query"]["search"]
    except (requests.exceptions.RequestException, KeyError, ValueError) as e:
        return (
            f"Wikipedia search failed ({type(e).__name__}). "
            "No Wikipedia results are available for this query."
        )

    if not results:
        return "No Wikipedia results found."

    output = []

    # Get information from the first 3 results
    for result in results[:3]:

        title = result["title"]

        try:
            page_response = requests.get(
                url,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "explaintext": True,
                    "exintro": True,
                    "titles": title,
                    "format": "json"
                },
                headers=headers,
                timeout=20
            )

            page_response.raise_for_status()

            page_data = page_response.json()

            pages = page_data["query"]["pages"]

            page = next(iter(pages.values()))
        except (requests.exceptions.RequestException, KeyError, ValueError, StopIteration):
            # Skip this one page and keep the others.
            continue

        extract = page.get("extract", "No summary available.")

        page_url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")

        output.append(
            f"Title: {title}\nURL: {page_url}\nInformation: {extract[:1500]}"
        )

    if not output:
        return "Wikipedia pages could not be retrieved for this query."

    return "\n\n".join(output)


# 3. Initialize Wikipedia Tool
wikipedia_tool = Tool(
    name="wikipedia",
    func=search_wikipedia,
    description="Search Wikipedia for reliable background information"
)