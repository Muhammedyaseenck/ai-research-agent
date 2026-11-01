import re
from dotenv import load_dotenv
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor

from tools import search_tool, wikipedia_tool


# Load environment variables
load_dotenv()


# 1. Define structured output
class ResearchResponse(BaseModel):
    topic: str
    summary: str
    sources: list[str]
    tools_used: list[str]


# 2. Initialize Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-3.5-flash",
    timeout=60,
    max_retries=2,
)


# 3. Initialize output parser
parser = PydanticOutputParser(
    pydantic_object=ResearchResponse
)


# 4. Create prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            You are an intelligent research assistant.

            Your job is to research topics and generate
            accurate research responses.

            Instructions:
            - Use the search tool when web research is needed.
            - Use Wikipedia when relevant.
            - Base your summary on retrieved information.
            - Never invent sources.
            - Include the actual sources used.
            - Clearly explain research findings.
            - Mention the tools actually used.
            - If information cannot be verified, say so.

            Wrap the output in this format and provide no other text:

            {format_instructions}
            """
        ),
        ("placeholder", "{chat_history}"),
        ("human", "{query}"),
        ("placeholder", "{agent_scratchpad}")
    ]
).partial(
    format_instructions=parser.get_format_instructions()
)


# 5. Register tools
tools = [search_tool, wikipedia_tool]


# 6. Create tool calling agent
agent = create_tool_calling_agent(
    llm=llm,
    prompt=prompt,
    tools=tools
)


# 7. Create Agent Executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    return_intermediate_steps=True,  # keep a record of every tool call
    max_iterations=6,                # stop runaway tool loops
    handle_parsing_errors=True,      # don't crash on a malformed model reply
)

# Helper: read the agent's execution trace and return what really happened
def collect_evidence(intermediate_steps):
    tools_used = []
    sources = []
    for action, observation in intermediate_steps:
        if action.tool not in tools_used:
            tools_used.append(action.tool)
        for url in re.findall(r"^URL: (\S+)", str(observation), flags=re.MULTILINE):
            if url not in sources:
                sources.append(url)
    return tools_used, sources

# Helper: turn Gemini's output into a clean JSON string
def extract_text(output):
    # Case 1: output is a list of content blocks
    if isinstance(output, list):
        parts = []
        for block in output:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        text = "".join(parts)
    else:
        # Case 2: output is already a string
        text = str(output)

    text = text.strip()

    # Remove Markdown code fences like ```json ... ```
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]

    return text.strip()

# 8. Reusable function: run the agent and return a structured result
def run_agent(query, chat_history=None):
    raw_response = agent_executor.invoke(
        {
            "query": query,
            "chat_history": chat_history or [],
        }
    )

    # Parse the structured response
    structured_response = parser.parse(
        extract_text(raw_response.get("output"))
    )

    # Overwrite the model's self-reported tools and sources with what really happened
    real_tools, real_sources = collect_evidence(
        raw_response.get("intermediate_steps", [])
    )
    structured_response.tools_used = real_tools
    structured_response.sources = real_sources

    # Flag answers that no tool backed up
    if not real_sources:
        structured_response.summary += (
            "\n\nNote: no tools were used for this answer, so it could not be "
            "verified against retrieved sources."
        )

    return structured_response 


# 9. Terminal mode (only runs when you type: python main.py)
if __name__ == "__main__":

    query = input("What can I help you research? ")

    try:
        result = run_agent(query)

        print("\n========== RESEARCH PAPER ==========\n")

        print("TOPIC:")
        print(result.topic)

        print("\nSUMMARY:")
        print(result.summary)

        print("\nSOURCES:")
        for source in result.sources:
            print("-", source)

        print("\nTOOLS USED:")
        for tool in result.tools_used:
            print("-", tool)

        print("\n====================================")

    except Exception as e:
        print("Error:", e)