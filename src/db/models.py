"""
Ten31 Thoughts - Database Models
SQLAlchemy models for feeds, content, thesis elements, frameworks, and predictions.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Float, Boolean, JSON,
    ForeignKey, Index, Enum as SAEnum, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, Session, sessionmaker
import enum


Base = declarative_base()


# ─── Enums ───

class FeedCategory(str, enum.Enum):
    OUR_THESIS = "our_thesis"
    EXTERNAL_INTERVIEW = "external_interview"


class FeedStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class AnalysisStatus(str, enum.Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    ERROR = "error"
    SKIPPED = "skipped"


class ConnectionRelation(str, enum.Enum):
    REINFORCES = "reinforces"
    EXTENDS = "extends"
    COMPLICATES = "complicates"
    CONTRADICTS = "contradicts"
    ECHOES_MECHANISM = "echoes_mechanism"


class ConvictionLevel(str, enum.Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    SPECULATIVE = "speculative"


class PredictionStatus(str, enum.Enum):
    PENDING = "pending"
    PARTIALLY_VALIDATED = "partially_validated"
    VALIDATED = "validated"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


class ThesisAlignment(str, enum.Enum):
    AGREE = "agree"
    PARTIAL = "partial"
    DIVERGE = "diverge"
    UNRELATED = "unrelated"


# ─── Models ───

def gen_id():
    return str(uuid.uuid4())


class Feed(Base):
    """RSS/Atom feed source configuration."""
    __tablename__ = "feeds"

    feed_id = Column(String, primary_key=True, default=gen_id)
    url = Column(Text, nullable=False, unique=True)
    category = Column(SAEnum(FeedCategory), nullable=False)
    display_name = Column(String, nullable=False)
    tags = Column(JSON, default=list)
    poll_interval_minutes = Column(Integer, default=30)
    status = Column(SAEnum(FeedStatus), default=FeedStatus.ACTIVE)
    last_fetched = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    items = relationship("ContentItem", back_populates="feed", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Feed {self.display_name} ({self.category.value})>"


class ContentItem(Base):
    """Individual piece of content from a feed (article, episode, etc.)."""
    __tablename__ = "content_items"

    item_id = Column(String, primary_key=True, default=gen_id)
    feed_id = Column(String, ForeignKey("feeds.feed_id"), nullable=False)
    url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    published_date = Column(DateTime, nullable=True)
    authors = Column(JSON, default=list)
    summary = Column(Text, nullable=True)
    content_text = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    content_type = Column(String, default="article")  # article, podcast_transcript, audio
    audio_url = Column(Text, nullable=True)
    analysis_status = Column(SAEnum(AnalysisStatus), default=AnalysisStatus.PENDING)
    analysis_error = Column(Text, nullable=True)
    analyzed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    feed = relationship("Feed", back_populates="items")
    thesis_elements = relationship("ThesisElement", back_populates="content_item", cascade="all, delete-orphan")
    external_frameworks = relationship("ExternalFramework", back_populates="content_item", cascade="all, delete-orphan")
    blind_spots = relationship("BlindSpot", back_populates="content_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_content_hash", "content_hash"),
        Index("idx_content_feed_date", "feed_id", "published_date"),
        Index("idx_content_status", "analysis_status"),
    )

    def __repr__(self):
        return f"<ContentItem {self.title[:50]}>"


class ThesisElement(Base):
    """
    Extracted thesis element from 'our_thesis' content.
    Represents a specific macro claim, position, or prediction.
    """
    __tablename__ = "thesis_elements"

    element_id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("content_items.item_id"), nullable=False)
    claim_text = Column(Text, nullable=False)
    topic = Column(String, nullable=False)  # fed_policy, labor, fiscal, geopolitics, bitcoin, etc.
    conviction = Column(SAEnum(ConvictionLevel), default=ConvictionLevel.MODERATE)
    is_prediction = Column(Boolean, default=False)
    prediction_outcome = Column(Text, nullable=True)
    prediction_status = Column(SAEnum(PredictionStatus), default=PredictionStatus.PENDING)
    prediction_horizon = Column(String, nullable=True)  # "3 months", "end of year", etc.
    is_data_skepticism = Column(Boolean, default=False)
    data_series = Column(String, nullable=True)  # NFP, CPI, GDP, etc.
    alternative_interpretation = Column(Text, nullable=True)
    thread_id = Column(String, nullable=True)  # links related elements across editions
    raw_excerpt = Column(Text, nullable=True)  # original text from the newsletter
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_item = relationship("ContentItem", back_populates="thesis_elements")

    __table_args__ = (
        Index("idx_thesis_topic", "topic"),
        Index("idx_thesis_thread", "thread_id"),
        Index("idx_thesis_prediction", "is_prediction", "prediction_status"),
    )


class ExternalFramework(Base):
    """
    Extracted framework from 'external_interview' content.
    Represents a mental model, analytical lens, or decision framework.
    """
    __tablename__ = "external_frameworks"

    framework_id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("content_items.item_id"), nullable=False)
    framework_name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    guest_name = Column(String, nullable=True)
    causal_chain = Column(JSON, nullable=True)  # {"if": "X", "then": "Y", "because": "Z"}
    key_indicators = Column(JSON, default=list)  # data points the guest watches
    time_horizon = Column(String, nullable=True)  # cyclical, secular, structural
    thesis_alignment = Column(SAEnum(ThesisAlignment), default=ThesisAlignment.UNRELATED)
    alignment_notes = Column(Text, nullable=True)
    reasoning_score = Column(Float, nullable=True)  # 0-1 quality score
    reasoning_notes = Column(Text, nullable=True)
    predictions = Column(JSON, default=list)  # list of prediction objects
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_item = relationship("ContentItem", back_populates="external_frameworks")

    __table_args__ = (
        Index("idx_framework_guest", "guest_name"),
        Index("idx_framework_alignment", "thesis_alignment"),
    )


class BlindSpot(Base):
    """Detected blind spot - something that should have been discussed but wasn't."""
    __tablename__ = "blind_spots"

    spot_id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("content_items.item_id"), nullable=False)
    topic = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    macro_event = Column(Text, nullable=True)  # related event that was occurring
    event_date = Column(DateTime, nullable=True)
    severity = Column(String, default="medium")  # low, medium, high
    source_type = Column(String, nullable=False)  # our_thesis, external, mutual
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    content_item = relationship("ContentItem", back_populates="blind_spots")

    __table_args__ = (
        Index("idx_blindspot_topic", "topic"),
        Index("idx_blindspot_severity", "severity"),
    )


class ConvergenceRecord(Base):
    """Records agreement/divergence between thesis elements and external frameworks."""
    __tablename__ = "convergence_records"

    record_id = Column(String, primary_key=True, default=gen_id)
    thesis_element_id = Column(String, ForeignKey("thesis_elements.element_id"), nullable=False)
    framework_id = Column(String, ForeignKey("external_frameworks.framework_id"), nullable=False)
    alignment_type = Column(String, nullable=False)  # agree_diff_reasoning, agree_same, partial, diverge
    divergence_point = Column(Text, nullable=True)
    competing_assumptions = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WeeklyBriefing(Base):
    """Generated weekly briefing document metadata."""
    __tablename__ = "weekly_briefings"

    briefing_id = Column(String, primary_key=True, default=gen_id)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    top_frameworks = Column(JSON, nullable=True)  # ranked list with scores
    thesis_scorecard = Column(JSON, nullable=True)
    convergence_summary = Column(JSON, nullable=True)
    blind_spot_alerts = Column(JSON, nullable=True)
    narrative_shifts = Column(JSON, nullable=True)
    file_path_pdf = Column(Text, nullable=True)
    file_path_docx = Column(Text, nullable=True)
    items_ingested = Column(Integer, default=0)
    items_analyzed = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PredictionMarketLink(Base):
    """
    Links thesis predictions to prediction market contracts.
    Enables automated resolution via market outcomes.
    """
    __tablename__ = "prediction_market_links"

    link_id = Column(String, primary_key=True, default=gen_id)
    element_id = Column(String, ForeignKey("thesis_elements.element_id"), nullable=True)
    framework_id = Column(String, ForeignKey("external_frameworks.framework_id"), nullable=True)
    platform = Column(String, nullable=False)  # polymarket, kalshi
    market_id = Column(String, nullable=False)
    market_slug = Column(String, nullable=True)
    market_title = Column(Text, nullable=False)
    market_url = Column(Text, nullable=True)
    price_at_link = Column(Float, nullable=True)  # probability when we linked it
    current_price = Column(Float, nullable=True)  # last known probability
    market_status = Column(String, default="open")  # open, closed, resolved
    market_result = Column(String, nullable=True)  # yes, no (after resolution)
    our_side = Column(String, nullable=True)  # yes, no - what we predicted
    match_confidence = Column(Float, nullable=True)  # 0-1 LLM confidence in match
    match_rationale = Column(Text, nullable=True)  # why LLM thinks this matches
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_market_link_element", "element_id"),
        Index("idx_market_link_platform", "platform"),
        Index("idx_market_link_status", "market_status"),
    )


class ResurfacingTrigger(str, enum.Enum):
    SCHEDULED = "scheduled"
    SEMANTIC_ON_WRITE = "semantic_on_write"
    NEWS_DRIVEN = "news_driven"


class Note(Base):
    """Personal note used by the resurfacing engine."""
    __tablename__ = "notes"

    note_id = Column(String, primary_key=True, default=gen_id)
    title = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    topic = Column(String, nullable=True)
    tags = Column(JSON, default=list)
    source_url = Column(Text, nullable=True)
    archived = Column(Boolean, default=False)
    # FSRS spaced-repetition fields
    fsrs_due = Column(DateTime, nullable=True)
    fsrs_stability = Column(Float, nullable=True)
    fsrs_difficulty = Column(Float, nullable=True)
    fsrs_state = Column(Integer, default=0)
    fsrs_reps = Column(Integer, default=0)
    fsrs_lapses = Column(Integer, default=0)
    fsrs_last_review = Column(DateTime, nullable=True)
    # v3 source tracking
    source = Column(String, nullable=True)  # "manual" | "timestamp" | "promoted_from_connection" | "promoted_from_signal"
    source_item_id = Column(String, ForeignKey("content_items.item_id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    resurfacing_events = relationship(
        "ResurfacingEvent", back_populates="note",
        foreign_keys="[ResurfacingEvent.note_id]",
        cascade="all, delete-orphan",
    )
    source_item = relationship("ContentItem", foreign_keys=[source_item_id])

    __table_args__ = (
        Index("idx_note_topic", "topic"),
        Index("idx_note_archived", "archived"),
        Index("idx_note_fsrs_due", "fsrs_due"),
    )


class ResurfacingEvent(Base):
    """Record of a note being surfaced to the user."""
    __tablename__ = "resurfacing_events"

    event_id = Column(String, primary_key=True, default=gen_id)
    note_id = Column(String, ForeignKey("notes.note_id"), nullable=False)
    trigger = Column(SAEnum(ResurfacingTrigger), nullable=False)
    trigger_item_id = Column(String, ForeignKey("content_items.item_id"), nullable=True)
    trigger_note_id = Column(String, ForeignKey("notes.note_id"), nullable=True)
    similarity_score = Column(Float, nullable=True)
    bridge_text = Column(Text, nullable=True)
    surfaced_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    digest_date = Column(DateTime, nullable=True)
    engaged_at = Column(DateTime, nullable=True)
    dismissed_at = Column(DateTime, nullable=True)
    rating = Column(Integer, nullable=True)

    # Relationships
    note = relationship("Note", back_populates="resurfacing_events", foreign_keys=[note_id])

    __table_args__ = (
        Index("idx_resurfacing_note", "note_id"),
        Index("idx_resurfacing_trigger", "trigger"),
        Index("idx_resurfacing_digest", "digest_date"),
    )


class Connection(Base):
    """Connection between a content item and a note — the core v3 primitive."""
    __tablename__ = "connections"

    connection_id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("content_items.item_id"), nullable=False)
    note_id = Column(String, ForeignKey("notes.note_id"), nullable=False)

    # One of: "reinforces" | "extends" | "complicates" | "contradicts" | "echoes_mechanism"
    relation = Column(String, nullable=False)

    articulation = Column(Text, nullable=False)  # 3-5 sentence prose bridge
    excerpt = Column(Text, nullable=True)  # source passage
    excerpt_location = Column(String, nullable=True)  # timestamp, page, etc.
    principles_invoked = Column(JSON, default=list)  # list of axiom IDs

    user_rating = Column(Integer, nullable=True)  # 1-5, null = unrated
    user_promoted_to_note = Column(Boolean, default=False)
    user_dismissed = Column(Boolean, default=False)

    strength = Column(Float, nullable=False)  # LLM confidence 0-1
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    item = relationship("ContentItem")
    note = relationship("Note")

    __table_args__ = (
        Index("idx_conn_item", "item_id"),
        Index("idx_conn_note", "note_id"),
        Index("idx_conn_rating", "user_rating"),
    )


class UnconnectedSignal(Base):
    """Signal from content that doesn't connect to any existing note."""
    __tablename__ = "unconnected_signals"

    signal_id = Column(String, primary_key=True, default=gen_id)
    item_id = Column(String, ForeignKey("content_items.item_id"), nullable=False)

    topic_summary = Column(Text, nullable=False)
    why_it_matters = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=True)

    user_dismissed = Column(Boolean, default=False)
    user_promoted_to_note = Column(Boolean, default=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    item = relationship("ContentItem")


class Digest(Base):
    """Generated weekly digest document."""
    __tablename__ = "digests"

    digest_id = Column(String, primary_key=True, default=gen_id)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    html_content = Column(Text, nullable=False)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class GuestProfile(Base):
    """Profile metadata for external guests — social links, bio, ELO rating."""
    __tablename__ = "guest_profiles"

    guest_name = Column(String, primary_key=True)
    display_name = Column(String, nullable=True)  # normalized display name
    x_handle = Column(String, nullable=True)  # Twitter/X handle without @
    linkedin_url = Column(Text, nullable=True)
    website_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)  # short bio/title
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
    # ELO rating fields
    elo_rating = Column(Float, default=1500.0)  # starting ELO like chess
    elo_peak = Column(Float, default=1500.0)
    elo_floor = Column(Float, default=1500.0)
    elo_predictions_counted = Column(Integer, default=0)
    elo_history = Column(JSON, default=list)  # list of {date, rating, delta, prediction, market_price, outcome}


# ─── Database Setup ───

def get_engine(db_path: str = None):
    import os
    if db_path is None:
        db_path = os.getenv("DATABASE_URL", "sqlite:///data/ten31thoughts.db")
    return create_engine(db_path, echo=False)


def create_tables(engine):
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
