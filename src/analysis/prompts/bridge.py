"""
Prompts for news-driven resurfacing bridge text generation.
"""

NEWS_DRIVEN_BRIDGE_SYSTEM = (
    "You write one-sentence bridges connecting a new piece of content to a "
    "previously-stored note. Dry, analytical, Ten31 Timestamp voice. No "
    "'This is interesting because' or 'Fascinatingly'. Just the bridge "
    "itself. 25 words maximum."
)

NEWS_DRIVEN_BRIDGE_USER = (
    "Content: {item_title} by {authors} ({date}).\n\n"
    "Content excerpt: {content_excerpt}\n\n"
    "Stored note: {note_body}\n\n"
    "Write one sentence (<= 25 words) explaining why the user should "
    "reread this note in light of this content."
)
