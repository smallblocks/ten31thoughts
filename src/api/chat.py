"""
Ten31 Thoughts - Chat API
RAG-powered chat interface for querying the intelligence layer.
Combines vector search, structured data queries, and LLM generation.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db.models import (
    ContentItem, ThesisElement, ExternalFramework, BlindSpot,
    WeeklyBriefing, Feed, FeedCategory
)
from ..db.session import get_db
from ..db.vector import VectorStore
from ..llm.router import LLMRouter

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

4. Deploy dry wit sparingly and only when it reveals something true. "Pro-tax advocates
   recoiled in horror at the bill's potential to deprive the government of tens of tax
   dollars" works because it makes a substantive point through irony. Do not force humor.

5. Use parenthetical asides to deliver the real point inside what looks like a subordinate
   clause: "(though heightened borrowing from both the Discount Window and the new BTFP
   facility persisted)" — this is how the Timestamp hides its sharpest observations in
   plain sight. Do this.

6. Contextualize against structural time, not news cycles. Reference decades, centuries,
   historical patterns. "This represents the latest instance of a long-established pattern"
   is how the Timestamp writes. Not "this is happening now."

7. Show institutional skepticism. When official data or narratives are cited, note what
   they conveniently omit: "While some of the wide miss can likely be attributed to storm
   activity and a strike at Boeing, the weaker than expected report also included significant
   downward revisions for numbers from both August and September." Acknowledge the official
   excuse, then present the structural reality underneath it.

8. When citing sources from the database, use this format naturally in prose:
   "As [Guest Name] argued on MacroVoices [date]..." or "The [date] edition of the
   Timestamp noted that..." Do not use bracketed citation formats. Weave sources into
   the prose the way a newsletter writer would.

9. State your thesis conviction plainly when relevant, without hedging or cheerleading:
   "anyone fading this is missing the forest for the trees" — not "we believe this could
   potentially be significant." No weasel words.

10. End substantive responses with either an actionable observation ("this is worth
    watching because...") or a structural framing ("the pattern here is the same one
    that has played out in every late-cycle environment since..."). Never end with
    "I hope this helps!" or "Let me know if you have questions!"

YOUR ANALYTICAL FRAMEWORK:
You evaluate everything through first principles drawn from the classical tradition:
- SOUND MONEY: Aristotle, Copernicus, Oresme, Menger, Mises, Hayek — debasement is the
  default state trajectory, not an aberration
- POLITICAL CYCLES: Polybius, Cicero, Machiavelli, Gibbon — republics decay, empires
  overextend, institutional stability must be maintained rather than assumed
- HUMAN NATURE: Thucydides, Smith, Bastiat, Sowell — incentives drive behavior, dispersed
  knowledge cannot be centralized, every policy has unseen costs
- PROPERTY RIGHTS: Locke, Montesquieu, de Soto — security of property is the foundation
  of prosperity

Reference these thinkers when their principles are directly relevant — not as decoration
but as genuine intellectual engagement that clarifies the analysis.

WHAT YOU HAVE ACCESS TO:
- The full archive of Ten31 Timestamp newsletter editions
- MacroVoices and other external podcast transcripts with framework analysis
- First-principles evaluations scoring every external framework against classical axioms
- Convergence analysis showing where the Ten31 thesis aligns or diverges with external voices
- Blind spot detection highlighting topics that are systematically under-discussed
- Prediction tracking with market-adjudicated outcomes via Polymarket and Kalshi

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


class ContextBuilder:
    """Builds RAG context for chat responses by combining vector search with structured queries."""

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

        # Detect query intent for targeted retrieval
        intent = self._classify_intent(query)

        # Vector search across all collections
        if intent in ("general", "comparison", "framework"):
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

        # Thesis elements search
        if intent in ("general", "thesis", "prediction", "comparison"):
            thesis_results = self.vs.search_thesis_elements(query, n_results=5)
            if thesis_results:
                context_parts.append("\n=== Our Thesis Elements ===")
                for r in thesis_results:
                    meta = r["metadata"]
                    context_parts.append(
                        f"[Topic: {meta.get('topic', '')} | "
                        f"Conviction: {meta.get('conviction', '')} | "
                        f"Prediction: {meta.get('is_prediction', False)}]\n{r['document'][:500]}"
                    )
                    sources.append({
                        "type": "thesis_element",
                        "topic": meta.get("topic", ""),
                        "conviction": meta.get("conviction", ""),
                    })

        # Framework search
        if intent in ("general", "framework", "comparison", "guest"):
            fw_results = self.vs.search_frameworks(query, n_results=5)
            if fw_results:
                context_parts.append("\n=== External Frameworks ===")
                for r in fw_results:
                    meta = r["metadata"]
                    context_parts.append(
                        f"[Guest: {meta.get('guest_name', '')} | "
                        f"Score: {meta.get('reasoning_score', 'N/A')}]\n{r['document'][:500]}"
                    )
                    sources.append({
                        "type": "framework",
                        "guest_name": meta.get("guest_name", ""),
                        "reasoning_score": meta.get("reasoning_score"),
                    })

        # Blind spot search
        if intent in ("general", "blindspot"):
            spot_results = self.vs.search_blind_spots(query, n_results=3)
            if spot_results:
                context_parts.append("\n=== Blind Spots ===")
                for r in spot_results:
                    meta = r["metadata"]
                    context_parts.append(
                        f"[Severity: {meta.get('severity', '')} | "
                        f"Type: {meta.get('source_type', '')}]\n{r['document'][:400]}"
                    )
                    sources.append({
                        "type": "blind_spot",
                        "severity": meta.get("severity", ""),
                    })

        # Add latest briefing context if relevant
        if intent in ("general", "framework", "briefing"):
            briefing = self._get_latest_briefing_context()
            if briefing:
                context_parts.append(f"\n=== Latest Weekly Briefing ===\n{briefing}")

        # Add scorecard if prediction-related
        if intent in ("prediction", "scorecard"):
            scorecard = self._get_scorecard_context()
            if scorecard:
                context_parts.append(f"\n=== Prediction Scorecard ===\n{scorecard}")

        context = "\n\n".join(context_parts)
        return context, sources

    def _classify_intent(self, query: str) -> str:
        """Classify the query intent for targeted retrieval."""
        q = query.lower()

        if any(w in q for w in ["top 5", "framework", "rank", "best model"]):
            return "framework"
        if any(w in q for w in ["predict", "accuracy", "scorecard", "track record", "validated"]):
            return "prediction"
        if any(w in q for w in ["blind spot", "missing", "not talking", "overlooked"]):
            return "blindspot"
        if any(w in q for w in ["disagree", "diverge", "compare", "vs", "versus", "difference"]):
            return "comparison"
        if any(w in q for w in ["my view", "our thesis", "our position", "we think", "timestamp"]):
            return "thesis"
        if any(w in q for w in ["briefing", "weekly", "summary", "this week"]):
            return "briefing"
        if any(w in q for w in ["scorecard", "score"]):
            return "scorecard"
        # Check for guest names
        if any(w in q for w in ["who", "guest", "said"]):
            return "guest"

        return "general"

    def _get_latest_briefing_context(self) -> Optional[str]:
        """Get summary of latest briefing for context."""
        briefing = self.session.execute(
            select(WeeklyBriefing)
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not briefing:
            return None

        parts = [f"Week of {briefing.week_start.strftime('%Y-%m-%d')}:"]

        if briefing.top_frameworks:
            parts.append("Top frameworks: " + ", ".join(
                f"{fw.get('framework_name', '')} ({fw.get('composite_score', 0):.2f})"
                for fw in briefing.top_frameworks[:5]
            ))

        if briefing.blind_spot_alerts:
            mutual = briefing.blind_spot_alerts.get("recent_mutual", [])
            if mutual:
                parts.append("Blind spots: " + ", ".join(
                    s.get("topic", "") for s in mutual[:3]
                ))

        return "\n".join(parts)

    def _get_scorecard_context(self) -> Optional[str]:
        """Get scorecard summary for context."""
        briefing = self.session.execute(
            select(WeeklyBriefing)
            .where(WeeklyBriefing.thesis_scorecard.isnot(None))
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if not briefing or not briefing.thesis_scorecard:
            return None

        card = briefing.thesis_scorecard.get("thesis", {})
        accuracy = card.get("accuracy_rate")
        return (
            f"Our accuracy rate: {accuracy:.0%}\n" if accuracy else ""
        ) + f"Total predictions tracked: {card.get('total', 0)}"


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

    # Generate response
    response_text = await llm.complete(
        task="chat",
        messages=messages,
        system=CHAT_SYSTEM,
    )

    return ChatResponse(
        response=response_text,
        sources=sources[:10],
        metadata={
            "context_scope": request.context_scope or "auto",
            "sources_used": len(sources),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.get("/briefings")
def list_briefings(
    limit: int = 20,
    session: Session = Depends(get_db),
):
    """List available weekly briefings."""
    briefings = session.execute(
        select(WeeklyBriefing)
        .order_by(WeeklyBriefing.created_at.desc())
        .limit(limit)
    ).scalars().all()

    return [
        {
            "briefing_id": b.briefing_id,
            "week_start": b.week_start.isoformat() if b.week_start else None,
            "week_end": b.week_end.isoformat() if b.week_end else None,
            "items_ingested": b.items_ingested,
            "items_analyzed": b.items_analyzed,
            "has_pdf": bool(b.file_path_pdf),
            "has_frameworks": bool(b.top_frameworks),
            "created_at": b.created_at.isoformat(),
        }
        for b in briefings
    ]


@router.get("/briefings/latest")
def get_latest_briefing(session: Session = Depends(get_db)):
    """Get the latest weekly briefing with full data."""
    briefing = session.execute(
        select(WeeklyBriefing)
        .order_by(WeeklyBriefing.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not briefing:
        raise HTTPException(status_code=404, detail="No briefings generated yet")

    return {
        "briefing_id": briefing.briefing_id,
        "week_start": briefing.week_start.isoformat(),
        "week_end": briefing.week_end.isoformat(),
        "top_frameworks": briefing.top_frameworks,
        "thesis_scorecard": briefing.thesis_scorecard,
        "convergence_summary": briefing.convergence_summary,
        "blind_spot_alerts": briefing.blind_spot_alerts,
        "narrative_shifts": briefing.narrative_shifts,
        "items_ingested": briefing.items_ingested,
        "items_analyzed": briefing.items_analyzed,
        "file_path_pdf": briefing.file_path_pdf,
        "created_at": briefing.created_at.isoformat(),
    }
