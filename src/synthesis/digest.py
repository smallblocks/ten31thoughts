"""
Ten31 Thoughts - Weekly Digest Generator
Six-section digest anchored to Notes and Connections.
Replaces the old BriefingGenerator with a note-centric format.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from ..db.models import (
    Connection, UnconnectedSignal, Note, ContentItem, Feed,
    ResurfacingEvent, FeedCategory, gen_id, Base,
    Digest,
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)

DIGEST_SYSTEM_PROMPT = """\
You are writing the weekly digest for Ten31, a bitcoin-focused investment platform.
Write in the Timestamp voice: analytical, not reportorial. Connect themes across sections.
Be direct, have conviction, and surface non-obvious patterns.

You will receive structured data for six sections. Write 800-1200 words of prose that:
1. Leads with the most important insight from the week
2. Weaves the connections, signals, and notes into a coherent narrative
3. Points out where threads are converging or diverging
4. Calls out what deserves more attention

Do NOT invent data. Every claim must be grounded in the structured data provided.
Return your response as a JSON object with these keys:
- "opening": A 2-3 sentence lead paragraph (the single most important takeaway)
- "connections_prose": Prose for the strongest connections section
- "threads_prose": Prose for the threads in motion section
- "signals_prose": Prose for the unconnected signals section
- "resurfaced_prose": Prose for the resurfaced notes section
- "wrote_prose": Prose for what you wrote this week
- "sources_prose": One sentence on source activity
"""


class DigestGenerator:
    """
    Generates a weekly digest with six sections anchored to Notes and Connections.
    """

    def __init__(self, llm_router: LLMRouter, session: Session):
        self.llm = llm_router
        self.session = session

    async def generate_weekly_digest(
        self,
        period_end: Optional[datetime] = None,
    ) -> dict:
        """
        Generate a six-section weekly digest.

        Returns:
            dict with keys: digest_id, period_start, period_end,
            sections (raw data), html_content, created_at
        """
        if period_end is None:
            period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=7)

        # Gather structured data for all six sections
        sections = {
            "strongest_connections": self._gather_connections(period_start, period_end),
            "threads_in_motion": self._gather_threads(period_start, period_end),
            "unconnected_signals": self._gather_signals(period_start, period_end),
            "notes_resurfaced": self._gather_resurfacing(period_start, period_end),
            "what_you_wrote": self._gather_written(period_start, period_end),
            "sources_active": self._gather_sources(period_start, period_end),
        }

        # LLM synthesis
        llm_prose = await self._synthesize(sections)

        # Render HTML
        html_content = self._render_html(sections, llm_prose, period_start, period_end)

        # Store
        digest = Digest(
            digest_id=gen_id(),
            period_start=period_start,
            period_end=period_end,
            html_content=html_content,
            raw_data=sections,
        )
        self.session.add(digest)
        self.session.commit()

        return {
            "digest_id": digest.digest_id,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "sections": sections,
            "html_content": html_content,
            "created_at": digest.created_at.isoformat(),
        }

    # ─── Section Gatherers ───

    def _gather_connections(self, start: datetime, end: datetime) -> list[dict]:
        """Section 1: Top 5 strongest connections this week."""
        connections = (
            self.session.query(Connection)
            .filter(Connection.created_at.between(start, end))
            .all()
        )

        scored = []
        for c in connections:
            rating = c.user_rating if c.user_rating is not None else 3
            score = c.strength * rating / 5.0
            item = c.item
            note = c.note
            scored.append({
                "connection_id": c.connection_id,
                "articulation": c.articulation,
                "relation": c.relation,
                "strength": c.strength,
                "user_rating": c.user_rating,
                "score": round(score, 4),
                "source_title": item.title if item else None,
                "source_date": item.published_date.isoformat() if item and item.published_date else None,
                "note_body": note.body if note else None,
                "note_title": note.title if note else None,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:5]

    def _gather_threads(self, start: datetime, end: datetime) -> list[dict]:
        """Section 2: Threads in motion — notes with thread:* tags that got new connections."""
        # Find notes with thread tags that have connections created this week
        notes_with_threads = (
            self.session.query(Note)
            .filter(Note.tags.isnot(None))
            .all()
        )

        threads: dict[str, dict] = {}
        for note in notes_with_threads:
            tags = note.tags or []
            thread_tags = [t for t in tags if isinstance(t, str) and t.startswith("thread:")]
            if not thread_tags:
                continue

            # Check for connections to this note in the period
            conns = (
                self.session.query(Connection)
                .filter(
                    Connection.note_id == note.note_id,
                    Connection.created_at.between(start, end),
                )
                .all()
            )
            if not conns:
                continue

            for tag in thread_tags:
                thread_name = tag.replace("thread:", "")
                if thread_name not in threads:
                    threads[thread_name] = {"thread": thread_name, "notes": [], "connections": []}

                threads[thread_name]["notes"].append({
                    "note_id": note.note_id,
                    "title": note.title,
                    "body": note.body[:200] if note.body else None,
                })
                for c in conns:
                    threads[thread_name]["connections"].append({
                        "connection_id": c.connection_id,
                        "relation": c.relation,
                        "articulation": c.articulation,
                        "source_title": c.item.title if c.item else None,
                    })

        return list(threads.values())

    def _gather_signals(self, start: datetime, end: datetime) -> list[dict]:
        """Section 3: Top 3 unconnected signals worth attention."""
        signals = (
            self.session.query(UnconnectedSignal)
            .filter(
                UnconnectedSignal.created_at.between(start, end),
                UnconnectedSignal.user_dismissed == False,
            )
            .order_by(UnconnectedSignal.created_at.desc())
            .limit(3)
            .all()
        )

        result = []
        for s in signals:
            item = s.item
            result.append({
                "signal_id": s.signal_id,
                "topic_summary": s.topic_summary,
                "why_it_matters": s.why_it_matters,
                "source_title": item.title if item else None,
            })
        return result

    def _gather_resurfacing(self, start: datetime, end: datetime) -> list[dict]:
        """Section 4: Notes resurfaced this week."""
        events = (
            self.session.query(ResurfacingEvent)
            .filter(ResurfacingEvent.surfaced_at.between(start, end))
            .all()
        )

        result = []
        for e in events:
            note = e.note
            result.append({
                "event_id": e.event_id,
                "note_body": note.body if note else None,
                "note_title": note.title if note else None,
                "trigger": e.trigger.value if hasattr(e.trigger, 'value') else str(e.trigger),
                "bridge_text": e.bridge_text,
                "similarity_score": e.similarity_score,
                "surfaced_at": e.surfaced_at.isoformat() if e.surfaced_at else None,
            })
        return result

    def _gather_written(self, start: datetime, end: datetime) -> dict:
        """Section 5: What you wrote — manual notes + Timestamp content."""
        manual_notes = (
            self.session.query(Note)
            .filter(
                Note.created_at.between(start, end),
                or_(
                    Note.source != "timestamp",
                    Note.source.is_(None),
                ),
            )
            .all()
        )

        timestamp_items = (
            self.session.query(ContentItem)
            .join(Feed, ContentItem.feed_id == Feed.feed_id)
            .filter(
                ContentItem.created_at.between(start, end),
                Feed.category == FeedCategory.OUR_THESIS,
            )
            .all()
        )

        return {
            "manual_notes": [
                {
                    "note_id": n.note_id,
                    "title": n.title,
                    "body": n.body[:300] if n.body else None,
                    "source": n.source,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in manual_notes
            ],
            "timestamp_items": [
                {
                    "item_id": i.item_id,
                    "title": i.title,
                    "published_date": i.published_date.isoformat() if i.published_date else None,
                }
                for i in timestamp_items
            ],
        }

    def _gather_sources(self, start: datetime, end: datetime) -> list[dict]:
        """Section 6: Sources active — content items by feed."""
        results = (
            self.session.query(
                Feed.display_name,
                func.count(ContentItem.item_id).label("count"),
            )
            .join(ContentItem, Feed.feed_id == ContentItem.feed_id)
            .filter(ContentItem.created_at.between(start, end))
            .group_by(Feed.display_name)
            .all()
        )

        return [{"feed_name": r[0], "count": r[1]} for r in results]

    # ─── LLM Synthesis ───

    async def _synthesize(self, sections: dict) -> dict:
        """Single LLM call to produce prose around the structured data."""
        user_message = json.dumps(sections, indent=2, default=str)

        try:
            result = await self.llm.complete_json(
                task="synthesis",
                messages=[{"role": "user", "content": user_message}],
                system=DIGEST_SYSTEM_PROMPT,
            )
            return result
        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return {
                "opening": "Digest synthesis unavailable this week.",
                "connections_prose": "",
                "threads_prose": "",
                "signals_prose": "",
                "resurfaced_prose": "",
                "wrote_prose": "",
                "sources_prose": "",
            }

    # ─── HTML Rendering ───

    def _render_html(
        self,
        sections: dict,
        prose: dict,
        period_start: datetime,
        period_end: datetime,
    ) -> str:
        """Render the digest as self-contained HTML with inline CSS."""
        week_str = (
            f"{period_start.strftime('%B %d')} — "
            f"{period_end.strftime('%B %d, %Y')}"
        )

        opening = prose.get("opening", "")

        # Section 1: Connections
        connections_html = ""
        for c in sections.get("strongest_connections", []):
            relation_badge = c.get("relation", "")
            connections_html += f"""
            <div class="card">
                <div class="badge">{relation_badge}</div>
                <p class="articulation">{c.get('articulation', '')}</p>
                <div class="meta">
                    Score: {c.get('score', 0):.2f} |
                    Source: {c.get('source_title', 'Unknown')} |
                    Note: {(c.get('note_title') or c.get('note_body', '')[:60])}
                </div>
            </div>
            """

        # Section 2: Threads
        threads_html = ""
        for t in sections.get("threads_in_motion", []):
            thread_conns = "".join(
                f"<li>{tc.get('relation', '')}: {tc.get('articulation', '')[:100]}</li>"
                for tc in t.get("connections", [])
            )
            threads_html += f"""
            <div class="card">
                <strong>Thread: {t.get('thread', '')}</strong>
                <ul>{thread_conns}</ul>
            </div>
            """

        # Section 3: Signals
        signals_html = ""
        for s in sections.get("unconnected_signals", []):
            signals_html += f"""
            <div class="card signal">
                <strong>{s.get('topic_summary', '')}</strong>
                <p>{s.get('why_it_matters', '')}</p>
                <div class="meta">Source: {s.get('source_title', 'Unknown')}</div>
            </div>
            """

        # Section 4: Resurfaced
        resurfaced_html = ""
        for r in sections.get("notes_resurfaced", []):
            resurfaced_html += f"""
            <div class="card">
                <strong>{r.get('note_title') or 'Note'}</strong>
                <p>{r.get('note_body', '')[:200]}</p>
                <div class="meta">
                    Trigger: {r.get('trigger', '')} |
                    {r.get('bridge_text', '') or ''}
                </div>
            </div>
            """

        # Section 5: What you wrote
        written = sections.get("what_you_wrote", {})
        written_html = ""
        for n in written.get("manual_notes", []):
            written_html += f"""
            <div class="card">
                <strong>{n.get('title') or 'Untitled note'}</strong>
                <p>{(n.get('body') or '')[:200]}</p>
            </div>
            """
        for i in written.get("timestamp_items", []):
            written_html += f"""
            <div class="card">
                <strong>Timestamp: {i.get('title', '')}</strong>
                <div class="meta">Published: {i.get('published_date', '')}</div>
            </div>
            """

        # Section 6: Sources
        sources = sections.get("sources_active", [])
        sources_html = ""
        for s in sources:
            sources_html += f"<li>{s.get('feed_name', 'Unknown')}: {s.get('count', 0)} items</li>"

        html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 800px; margin: 40px auto; padding: 20px; color: #333; line-height: 1.6; }}
    .header {{ text-align: center; margin-bottom: 40px; padding-bottom: 20px;
               border-bottom: 3px solid #1a1a2e; }}
    .header h1 {{ font-size: 32px; color: #1a1a2e; margin: 0; }}
    .header .subtitle {{ font-size: 16px; color: #666; margin: 8px 0; }}
    .header .period {{ font-size: 14px; color: #999; }}
    .opening {{ font-size: 16px; font-style: italic; color: #16213e;
                border-left: 4px solid #e94560; padding: 16px; margin: 24px 0;
                background: #fafafa; }}
    h2 {{ color: #16213e; border-bottom: 1px solid #eee; padding-bottom: 8px; margin-top: 32px; }}
    .card {{ background: #f8f9fa; border-left: 4px solid #e94560; padding: 16px;
             margin: 12px 0; border-radius: 0 6px 6px 0; }}
    .card.signal {{ border-left-color: #f59e0b; }}
    .badge {{ display: inline-block; background: #e94560; color: white;
              padding: 2px 8px; border-radius: 3px; font-size: 11px;
              text-transform: uppercase; margin-bottom: 8px; }}
    .articulation {{ font-size: 14px; margin: 8px 0; }}
    .meta {{ font-size: 12px; color: #888; margin-top: 8px; }}
    .prose {{ font-size: 14px; color: #444; margin: 8px 0 16px; }}
    .footer {{ text-align: center; margin-top: 40px; padding-top: 20px;
               border-top: 2px solid #e94560; font-size: 12px; color: #999; }}
    ul {{ padding-left: 20px; }}
    li {{ font-size: 13px; margin: 4px 0; }}
</style>
</head><body>

<div class="header">
    <h1>TEN31 THOUGHTS</h1>
    <p class="subtitle">Weekly Digest</p>
    <p class="period">{week_str}</p>
</div>

<div class="opening">{opening}</div>

<h2>Strongest Connections This Week</h2>
<div class="prose">{prose.get('connections_prose', '')}</div>
{connections_html or '<p class="meta">No connections this week.</p>'}

<h2>Threads in Motion</h2>
<div class="prose">{prose.get('threads_prose', '')}</div>
{threads_html or '<p class="meta">No active threads this week.</p>'}

<h2>Unconnected Signals Worth Your Attention</h2>
<div class="prose">{prose.get('signals_prose', '')}</div>
{signals_html or '<p class="meta">No unconnected signals this week.</p>'}

<h2>Notes Resurfaced This Week</h2>
<div class="prose">{prose.get('resurfaced_prose', '')}</div>
{resurfaced_html or '<p class="meta">No notes resurfaced this week.</p>'}

<h2>What You Wrote</h2>
<div class="prose">{prose.get('wrote_prose', '')}</div>
{written_html or '<p class="meta">Quiet writing week.</p>'}

<h2>Sources Active</h2>
<div class="prose">{prose.get('sources_prose', '')}</div>
{f'<ul>{sources_html}</ul>' if sources_html else '<p class="meta">No sources active this week.</p>'}

<div class="footer">
    Generated by Ten31 Thoughts v3.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
</div>

</body></html>"""

        return html
