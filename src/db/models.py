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


class GuestProfile(Base):
    """Profile metadata for external guests — social links, bio, etc."""
    __tablename__ = "guest_profiles"

    guest_name = Column(String, primary_key=True)
    display_name = Column(String, nullable=True)  # normalized display name
    x_handle = Column(String, nullable=True)  # Twitter/X handle without @
    linkedin_url = Column(Text, nullable=True)
    website_url = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)  # short bio/title
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


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
