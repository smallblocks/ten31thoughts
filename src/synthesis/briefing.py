"""
Ten31 Thoughts - Briefing Generator
Produces weekly structured briefing documents (HTML→PDF and DOCX).
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db.models import (
    WeeklyBriefing, ContentItem, Feed, FeedCategory, AnalysisStatus, gen_id
)
from ..convergence.alignment import AlignmentMapper
from ..convergence.validation import ValidationTracker
from ..convergence.blindspots import BlindSpotDetector
from ..convergence.narrative import NarrativeTracker
from ..llm.router import LLMRouter
from .frameworks import FrameworkRanker

logger = logging.getLogger(__name__)

BRIEFINGS_DIR = os.getenv("BRIEFINGS_DIR", "/data/briefings")


class BriefingGenerator:
    """
    Generates the weekly Ten31 Thoughts briefing document.
    Orchestrates all convergence modules and produces formatted output.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session
        self.ranker = FrameworkRanker(llm, session)
        self.alignment = AlignmentMapper(llm, session)
        self.validation = ValidationTracker(llm, session)
        self.blindspots = BlindSpotDetector(llm, session)
        self.narrative = NarrativeTracker(llm, session)

    async def generate_weekly_briefing(self) -> WeeklyBriefing:
        """
        Generate the full weekly briefing. Runs all synthesis steps and
        produces the briefing document.
        """
        week_end = datetime.now(timezone.utc)
        week_start = week_end - timedelta(days=7)

        logger.info(f"Generating briefing for {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}")

        # Step 1: Rank frameworks (Top 5)
        logger.info("Step 1/6: Ranking frameworks...")
        top_frameworks = await self.ranker.rank_frameworks(lookback_days=90)

        # Step 2: Get convergence summary
        logger.info("Step 2/6: Convergence mapping...")
        convergence = self.alignment.get_convergence_summary(days=14)

        # Step 3: Generate scorecard
        logger.info("Step 3/6: Prediction scorecard...")
        scorecard = self.validation.generate_scorecard(days=90)

        # Step 4: Blind spot summary
        logger.info("Step 4/6: Blind spot analysis...")
        blind_spots = self.blindspots.get_blind_spot_summary(days=14)

        # Step 5: Narrative shifts
        logger.info("Step 5/6: Narrative evolution...")
        narratives = self.narrative.get_narrative_summary(days=30)

        # Step 6: Ingestion stats
        logger.info("Step 6/6: Source activity...")
        source_stats = self._get_source_activity(week_start, week_end)

        # Create briefing record
        briefing = WeeklyBriefing(
            briefing_id=gen_id(),
            week_start=week_start,
            week_end=week_end,
            top_frameworks=top_frameworks,
            thesis_scorecard=scorecard,
            convergence_summary=convergence,
            blind_spot_alerts=blind_spots,
            narrative_shifts=narratives,
            items_ingested=source_stats["items_ingested"],
            items_analyzed=source_stats["items_analyzed"],
        )

        # Generate document files
        html_content = self._render_html(briefing, source_stats)
        file_paths = self._save_documents(briefing.briefing_id, html_content, week_end)
        briefing.file_path_pdf = file_paths.get("pdf")
        briefing.file_path_docx = file_paths.get("docx")

        self.session.add(briefing)
        self.session.commit()

        logger.info(f"Briefing generated: {briefing.briefing_id}")
        return briefing

    def _render_html(self, briefing: WeeklyBriefing, source_stats: dict) -> str:
        """Render the briefing as HTML for PDF conversion."""
        week_str = (
            f"{briefing.week_start.strftime('%B %d')} — "
            f"{briefing.week_end.strftime('%B %d, %Y')}"
        )

        sections = []

        # ── Header ──
        sections.append(f"""
        <div style="text-align:center; margin-bottom:40px; padding-bottom:20px; border-bottom:3px solid #1a1a2e;">
            <h1 style="font-size:32px; color:#1a1a2e; margin:0;">TEN31 THOUGHTS</h1>
            <p style="font-size:16px; color:#666; margin:8px 0;">Weekly Intelligence Briefing</p>
            <p style="font-size:14px; color:#999;">{week_str}</p>
        </div>
        """)

        # ── Section 1: Top 5 Frameworks ──
        frameworks = briefing.top_frameworks or []
        sections.append('<h2 style="color:#16213e;">Top 5 Macro Frameworks</h2>')
        if frameworks:
            for fw in frameworks[:5]:
                score = fw.get("composite_score", 0)
                bar_width = int(score * 100)
                alignment = fw.get("thesis_alignment", "unrelated")
                alignment_badge = {
                    "agree": '<span style="background:#d4edda;color:#155724;padding:2px 8px;border-radius:3px;font-size:11px;">ALIGNED</span>',
                    "partial": '<span style="background:#fff3cd;color:#856404;padding:2px 8px;border-radius:3px;font-size:11px;">PARTIAL</span>',
                    "diverge": '<span style="background:#f8d7da;color:#721c24;padding:2px 8px;border-radius:3px;font-size:11px;">DIVERGE</span>',
                }.get(alignment, '')

                sections.append(f"""
                <div style="background:#f8f9fa; border-left:4px solid #e94560; padding:16px; margin:12px 0; border-radius:0 6px 6px 0;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong style="font-size:15px;">#{fw.get('rank', '?')}. {fw.get('framework_name', 'Unknown')}</strong>
                        <span>{alignment_badge} <span style="color:#666;font-size:13px;">{fw.get('guest_name', '')}</span></span>
                    </div>
                    <div style="background:#ddd;height:6px;border-radius:3px;margin:8px 0;">
                        <div style="background:#e94560;height:6px;border-radius:3px;width:{bar_width}%;"></div>
                    </div>
                    <p style="font-size:13px;color:#555;margin:8px 0 0;">{fw.get('ranking_rationale', '')}</p>
                    <p style="font-size:13px;color:#16213e;margin:4px 0 0;"><strong>Key insight:</strong> {fw.get('key_insight', '')}</p>
                </div>
                """)
        else:
            sections.append('<p style="color:#666;">No frameworks ranked yet. More data needed.</p>')

        # ── Section 2: Thesis Scorecard ──
        scorecard = briefing.thesis_scorecard or {}
        thesis_card = scorecard.get("thesis", {})
        sections.append('<h2 style="color:#16213e;">Prediction Scorecard</h2>')

        accuracy = thesis_card.get("accuracy_rate")
        accuracy_str = f"{accuracy:.0%}" if accuracy is not None else "N/A"
        total = thesis_card.get("total", 0)
        validated = thesis_card.get("validated", 0)
        invalidated = thesis_card.get("invalidated", 0)

        sections.append(f"""
        <div style="display:flex; gap:16px; margin:12px 0;">
            <div style="flex:1;background:#f0f7ff;padding:16px;border-radius:8px;text-align:center;">
                <div style="font-size:28px;font-weight:bold;color:#16213e;">{accuracy_str}</div>
                <div style="font-size:12px;color:#666;">Our Accuracy</div>
            </div>
            <div style="flex:1;background:#f0fff4;padding:16px;border-radius:8px;text-align:center;">
                <div style="font-size:28px;font-weight:bold;color:#155724;">{validated}</div>
                <div style="font-size:12px;color:#666;">Validated</div>
            </div>
            <div style="flex:1;background:#fff5f5;padding:16px;border-radius:8px;text-align:center;">
                <div style="font-size:28px;font-weight:bold;color:#721c24;">{invalidated}</div>
                <div style="font-size:12px;color:#666;">Invalidated</div>
            </div>
            <div style="flex:1;background:#f8f9fa;padding:16px;border-radius:8px;text-align:center;">
                <div style="font-size:28px;font-weight:bold;color:#333;">{total}</div>
                <div style="font-size:12px;color:#666;">Total Tracked</div>
            </div>
        </div>
        """)

        # ── Section 3: Convergence Map ──
        convergence = briefing.convergence_summary or {}
        sections.append('<h2 style="color:#16213e;">Convergence Map</h2>')

        agreements = convergence.get("key_agreements", [])
        divergences = convergence.get("key_divergences", [])

        if agreements:
            sections.append('<h3 style="font-size:14px;color:#155724;">Key Agreements (different reasoning)</h3>')
            for ag in agreements[:3]:
                sections.append(f"""
                <div style="background:#f0fff4;padding:12px;margin:8px 0;border-radius:6px;font-size:13px;">
                    <strong>{ag.get('their_framework', '')}</strong> ({ag.get('guest', '')})<br/>
                    Our position: {ag.get('our_position', '')}
                </div>
                """)

        if divergences:
            sections.append('<h3 style="font-size:14px;color:#721c24;">Key Divergences</h3>')
            for dv in divergences[:3]:
                sections.append(f"""
                <div style="background:#fff5f5;padding:12px;margin:8px 0;border-radius:6px;font-size:13px;">
                    <strong>{dv.get('their_framework', '')}</strong> ({dv.get('guest', '')})<br/>
                    Divergence: {dv.get('divergence_point', 'Not specified')}
                </div>
                """)

        # ── Section 4: Blind Spot Alerts ──
        blind_spots = briefing.blind_spot_alerts or {}
        mutual = blind_spots.get("recent_mutual", [])
        sections.append('<h2 style="color:#16213e;">Blind Spot Alerts</h2>')

        if mutual:
            for spot in mutual[:5]:
                severity = spot.get("severity", "medium")
                severity_color = {"high": "#e94560", "medium": "#f59e0b", "low": "#666"}.get(severity, "#666")
                sections.append(f"""
                <div style="background:#fff8e1;border-left:4px solid {severity_color};padding:12px;margin:8px 0;border-radius:0 6px 6px 0;font-size:13px;">
                    <strong style="text-transform:uppercase;color:{severity_color};font-size:11px;">{severity}</strong>
                    <strong> {spot.get('topic', '')}</strong><br/>
                    {spot.get('description', '')[:200]}
                </div>
                """)
        else:
            sections.append('<p style="color:#666;">No mutual blind spots detected this week.</p>')

        # ── Section 5: Narrative Shifts ──
        narratives = briefing.narrative_shifts or {}
        sections.append('<h2 style="color:#16213e;">Narrative Shifts</h2>')

        for direction, label, color in [
            ("strengthening", "Conviction Strengthening", "#155724"),
            ("weakening", "Conviction Weakening", "#721c24"),
            ("pivoting", "Position Pivoting", "#856404"),
        ]:
            items = narratives.get(direction, [])
            if items:
                sections.append(f'<h3 style="font-size:14px;color:{color};">{label}</h3>')
                for item in items:
                    sections.append(f"""
                    <p style="font-size:13px;margin:4px 0;">
                        <strong>{item.get('thread', '')}</strong>: {item.get('latest', '')}
                    </p>
                    """)

        # ── Section 6: Source Activity ──
        sections.append('<h2 style="color:#16213e;">Source Activity</h2>')
        sections.append(f"""
        <p style="font-size:13px;color:#666;">
            Items ingested this week: {source_stats['items_ingested']} |
            Items analyzed: {source_stats['items_analyzed']} |
            Active feeds: {source_stats['active_feeds']}
        </p>
        """)

        # ── Footer ──
        sections.append(f"""
        <div style="text-align:center; margin-top:40px; padding-top:20px; border-top:2px solid #e94560;">
            <p style="font-size:12px; color:#999;">
                Generated by Ten31 Thoughts v2.0 | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
            </p>
        </div>
        """)

        html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; color: #333; line-height: 1.6; }}
    h2 {{ border-bottom: 1px solid #eee; padding-bottom: 8px; margin-top: 32px; }}
    h3 {{ margin-top: 16px; margin-bottom: 8px; }}
</style>
</head><body>
{''.join(sections)}
</body></html>"""

        return html

    def _save_documents(self, briefing_id: str, html: str, date: datetime) -> dict:
        """Save briefing as HTML (and PDF if WeasyPrint available)."""
        Path(BRIEFINGS_DIR).mkdir(parents=True, exist_ok=True)
        date_str = date.strftime("%Y-%m-%d")
        paths = {}

        # Always save HTML
        html_path = os.path.join(BRIEFINGS_DIR, f"briefing_{date_str}_{briefing_id[:8]}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        paths["html"] = html_path

        # Try PDF generation
        try:
            from weasyprint import HTML as WeasyHTML
            pdf_path = os.path.join(BRIEFINGS_DIR, f"briefing_{date_str}_{briefing_id[:8]}.pdf")
            WeasyHTML(string=html).write_pdf(pdf_path)
            paths["pdf"] = pdf_path
            logger.info(f"PDF briefing saved: {pdf_path}")
        except ImportError:
            logger.info("WeasyPrint not available, skipping PDF generation")
        except Exception as e:
            logger.warning(f"PDF generation failed: {e}")

        return paths

    def _get_source_activity(self, start: datetime, end: datetime) -> dict:
        """Get ingestion and analysis stats for the briefing period."""
        items_ingested = self.session.execute(
            select(func.count(ContentItem.item_id))
            .where(ContentItem.created_at.between(start, end))
        ).scalar() or 0

        items_analyzed = self.session.execute(
            select(func.count(ContentItem.item_id))
            .where(and_(
                ContentItem.analyzed_at.between(start, end),
                ContentItem.analysis_status == AnalysisStatus.COMPLETE,
            ))
        ).scalar() or 0

        from ..db.models import FeedStatus
        active_feeds = self.session.execute(
            select(func.count(Feed.feed_id))
            .where(Feed.status == FeedStatus.ACTIVE)
        ).scalar() or 0

        return {
            "items_ingested": items_ingested,
            "items_analyzed": items_analyzed,
            "active_feeds": active_feeds,
        }

    # ─── Query Methods ───

    def get_latest_briefing(self) -> Optional[WeeklyBriefing]:
        """Get the most recent weekly briefing."""
        return self.session.execute(
            select(WeeklyBriefing)
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_briefings(self, limit: int = 20) -> list[WeeklyBriefing]:
        """List recent briefings."""
        return list(self.session.execute(
            select(WeeklyBriefing)
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(limit)
        ).scalars().all())
