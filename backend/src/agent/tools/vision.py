import os
from pydantic_ai import Agent, BinaryContent
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps

image_analysis_agent = Agent(
    name="Image Analysis Agent",
    model=os.getenv("IMAGE_ANALYSIS_MODEL", "gpt-4o-mini"),
    system_prompt=(
        "Analyze the provided image URL and answer with factual, concise output. "
        "Do not hallucinate values; if uncertain, say so."
    ),
    output_retries=2,
)

async def analyze_image_content(
    ctx: RunContext[AgentDeps],
    image_url: str,
    question: str,
) -> str:
    """Download a PDF screenshot and use vision AI to extract structured content.

    Use this when a chunk references a table, diagram, or chart that cannot be
    understood from the text alone. Pass the screenshot URL from the chunk metadata
    and ask a specific question (e.g. "Extract all rows and columns from this table
    as key-value pairs with units").

    Returns the extracted text/data as a string.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            image_bytes = resp.content
            content_type = resp.headers.get("content-type", "image/png")

        result = await image_analysis_agent.run(
            [
                BinaryContent(data=image_bytes, media_type=content_type),
                question,
            ]
        )
        return result.response.text
    except Exception as exc:
        return f"Image analysis failed: {exc}"
