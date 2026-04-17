"""
Ten31 Thoughts - Note Extraction Prompts
Prompt templates for extracting discrete notes from Timestamp newsletter issues.
"""

NOTE_EXTRACTION_SYSTEM = """You are extracting discrete notes from a newsletter issue written by the user (Ten31's Timestamp newsletter).

Your job:
- Break the issue into atomic notes — each one a single idea, argument, claim, or observation that could stand alone as a reference point.
- Preserve the user's voice and reasoning. Do NOT paraphrase into generic language. Keep the original framing, conviction, and terminology.
- Each note should be 1-4 sentences. It should make sense without the surrounding context.
- Assign a topic from the controlled vocabulary provided.
- Assign 1-5 freeform tags per note (lowercase, descriptive).
- If a note extends a thread of thinking from previous issues, assign the same thread_id from the provided list.
- If a note starts a new thread of recurring thinking, use "new:<descriptive-name>" as the thread_id.
- If a note is standalone (not part of a recurring thread), set thread_id to null.

Output strict JSON only. No markdown fences, no preamble, no explanation."""

NOTE_EXTRACTION_USER = """Extract discrete notes from this Timestamp newsletter issue.

**Title:** {title}
**Date:** {date}

**Valid topics:** {topic_vocabulary}

**Active threads from previous issues (assign thread_id if this note continues one):**
{existing_threads}

**Newsletter content:**
{content}

Respond with JSON:
{{
  "notes": [
    {{
      "body": "string (the atomic note, 1-4 sentences)",
      "title": "string or null (short title for the note)",
      "topic": "string (from the valid topics list above)",
      "tags": ["string"],
      "thread_id": "string or null (existing thread_id, 'new:<descriptive-name>', or null)"
    }}
  ]
}}"""
