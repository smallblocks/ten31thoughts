"""
Ten31 Thoughts - Chat API
RAG-powered chat interface for querying the intelligence layer.
Combines vector search, structured data queries, LLM generation,
and web search via SearXNG.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db.models import ContentItem, Feed, FeedCategory
from ..db.session import get_db
from ..db.vector import VectorStore
from ..llm.router import LLMRouter
from ..llm.date_context import inject_date_context
from .search import execute_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


CHAT_SYSTEM = """You are the Ten31 Thoughts intelligence engine. You write and think in the
voice of the Ten31 Timestamp newsletter — the weekly macro intelligence report published
by the Ten31 team for their LPs and the broader bitcoin ecosystem.

YOUR VOICE:
You do not sound like an AI assistant. You sound like a sharp macro analyst at a
bitcoin-focused investment firm who has been steeped in Austrian economics, classical
political philosophy, and the structural case for bitcoin for a decade. You are writing
for an audience of sophisticated investors who will notice if you hedge, equivocate,
or pad your analysis with filler.

RULES — FOLLOW THESE WITHOUT EXCEPTION:

1. NEVER open with "Great question", "That's an interesting point", "Absolutely",
   "I'd be happy to help", or any variation. Open mid-thought with the substance.
   Start with the data, the verdict, or the observation. No preamble.

2. NEVER use the word "delve", "tapestry", "landscape" (as metaphor), "synergy",
   "holistic", "robust" (unless describing a literal system), or "I think" as a
   hedge. These are AI tells. Eliminate them.

3. Lead with specifics. Not "employment data was weak" but "the US added just 12,000
   jobs in October relative to 223,000 in the prior month and expectations for 100,000."
   Cite the number, the date, the source, the comparison.

4. Deploy dry wit sparingly and only when it reveals something true.

5. Use parenthetical asides to deliver the real point inside what looks like a subordinate
   clause.

6. Contextualize against structural time, not news cycles. Reference decades, centuries,
   historical patterns.

7. Show institutional skepticism. When official data or narratives are cited, note what
   they conveniently omit.

8. When citing sources from the database, use this format naturally in prose:
   "As [Guest Name] argued on MacroVoices [date]..." or "The [date] edition of the
   Timestamp noted that..." Do not use bracketed citation formats.

9. State your thesis conviction plainly when relevant, without hedging or cheerleading.

10. End substantive responses with either an actionable observation or a structural framing.
    Never end with "I hope this helps!" or "Let me know if you have questions!"

YOUR ANALYTICAL FRAMEWORK:
You evaluate everything through first principles drawn from the classical tradition:
- SOUND MONEY: Aristotle, Copernicus, Oresme, Menger, Mises, Hayek
- POLITICAL CYCLES: Polybius, Cicero, Machiavelli, Gibbon
- HUMAN NATURE: Thucydides, Smith, Bastiat, Sowell
- PROPERTY RIGHTS: Locke, Montesquieu, de Soto

WHAT YOU HAVE ACCESS TO:
- The full archive of Ten31 Timestamp newsletter editions
- External podcast transcripts
- Personal notes and connections between content and notes
- Unconnected signals worth watching

TOOLS:
You have access to a web_search tool that queries the internet via a local SearXNG instance.
Use it when you need current data not in the database.

The user is a macro analyst at Ten31. They want the sharpest possible analysis in the
voice of their own firm's research. Do not waste their time."""


class ChatRequest(BaseModel):
    message: str = Field(..., description="User's message")
    context_scope: Optional[str] = Field(
        None,
        description="Scope context: 'all', 'our_thesis', 'external', or None for auto"
    )


class ChatResponse(BaseModel):
    response: str
    sources: list[dict]
    metadata: dict


# ─── Tool Definitions ───

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current information. Use when you need real-time data like current prices, recent news, Fed announcements, or any information not in the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (1-10)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    }
]


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool and return the result as a string."""
    if name == "web_search":
        query = arguments.get("query", "")
        count = arguments.get("count", 5)
        results = await execute_search(query, count)

        if not results:
            return f"No results found for: {query}"

        formatted = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            formatted.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}\n")

        return "\n".join(formatted)

    return f"Unknown tool: {name}"


class ContextBuilder:
    """Builds RAG context for chat responses using notes, connections, content, and signals."""

    def __init__(self, session: Session, vector_store: VectorStore):
        self.session = session
        self.vs = vector_store

    def build_context(self, query: str, scope: Optional[str] = None) -> tuple[str, list[dict]]:
        """
        Build context string and source citations for a query.
        Returns (context_text, sources_list).
        """
        sources = []
        context_parts = []

        # Vector search: content chunks
        category = None
        if scope == "our_thesis":
            category = "our_thesis"
        elif scope == "external":
            category = "external_interview"

        content_results = self.vs.search_content(query, n_results=5, category=category)
        if content_results:
            context_parts.append("=== Relevant Content ===")
            for r in content_results:
                meta = r["metadata"]
                context_parts.append(
                    f"[{meta.get('title', 'Unknown')} | {meta.get('date', '')} | "
                    f"{meta.get('category', '')}]\n{r['document'][:800]}"
                )
                sources.append({
                    "type": "content",
                    "title": meta.get("title", ""),
                    "date": meta.get("date", ""),
                    "category": meta.get("category", ""),
                })

        # Notes
        note_results = self.vs.search_notes(query, n_results=5)
        if note_results:
            context_parts.append("\n=== Notes ===")
            for r in note_results:
                meta = r["metadata"]
                context_parts.append(
                    f"[Note: {meta.get('title', 'Untitled')} | "
                    f"Topic: {meta.get('topic', '')}]\n{r['document'][:500]}"
                )
                sources.append({
                    "type": "note",
                    "title": meta.get("title", ""),
                    "topic": meta.get("topic", ""),
                })

        # Connections
        conn_results = self.vs.search_connections(query, n_results=5)
        if conn_results:
            context_parts.append("\n=== Connections ===")
            for r in conn_results:
                meta = r["metadata"]
                context_parts.append(
                    f"[Connection: {meta.get('relation', '')} | "
                    f"Strength: {meta.get('strength', '')}]\n{r['document'][:500]}"
                )
                sources.append({
                    "type": "connection",
                    "relation": meta.get("relation", ""),
                })

        context = "\n\n".join(context_parts)
        return context, sources


# ─── Endpoints ───

@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest, session: Session = Depends(get_db)):
    """Send a message to the Ten31 Thoughts intelligence assistant."""
    llm = LLMRouter()

    try:
        vs = VectorStore()
    except Exception as e:
        logger.warning(f"Vector store unavailable: {e}. Using SQL-only context.")
        vs = None

    # Handle special commands
    if request.message.lower().startswith("add feed"):
        return ChatResponse(
            response="To add a feed, use the Feed Management UI or POST to /api/feeds/ with the feed URL and category.",
            sources=[],
            metadata={"intent": "feed_management"},
        )

    # Build RAG context
    sources = []
    context = ""
    if vs:
        ctx_builder = ContextBuilder(session, vs)
        context, sources = ctx_builder.build_context(
            request.message, scope=request.context_scope
        )

    # Build messages
    messages = []
    if context:
        messages.append({
            "role": "user",
            "content": (
                f"Here is relevant context from the Ten31 Thoughts intelligence database:\n\n"
                f"{context}\n\n"
                f"---\n\n"
                f"User question: {request.message}"
            )
        })
    else:
        messages.append({"role": "user", "content": request.message})

    # Generate response with tool support
    tool_calls_made = []
    max_tool_iterations = 3
    response_text = ""

    for iteration in range(max_tool_iterations):
        try:
            response = await llm.complete_with_tools(
                task="chat",
                messages=messages,
                system=inject_date_context(CHAT_SYSTEM),
                tools=TOOLS,
            )
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            response_text = "Sorry, there was an error processing your request. Please try again."
            break

        if response.get("tool_calls"):
            for tool_call in response["tool_calls"]:
                try:
                    tool_name = tool_call["function"]["name"]
                    tool_args = json.loads(tool_call["function"]["arguments"])

                    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                    tool_result = await execute_tool(tool_name, tool_args)
                    tool_calls_made.append({"tool": tool_name, "args": tool_args})

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [tool_call],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result,
                    })
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
        else:
            response_text = response.get("content") or ""
            break
    else:
        response_text = response.get("content") or "Unable to complete the request."

    if not response_text:
        response_text = "I wasn't able to generate a response. Please try rephrasing your question."

    return ChatResponse(
        response=response_text,
        sources=sources[:10],
        metadata={
            "context_scope": request.context_scope or "auto",
            "sources_used": len(sources),
            "tool_calls": tool_calls_made,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
