"""
Ten31 Thoughts - Extraction Engine Prompts
Extracts predictions and framework references from notes.
"""

EXTRACTION_SYSTEM = """You are an extraction engine for an investment thesis tracking system.

Your job is to parse a note — a thought, argument, or observation — and extract:
1. **Predictions**: Falsifiable claims about the future with timelines and measurable outcomes
2. **Framework References**: Links to named mental models or intellectual constructs

RULES:
- Only extract ACTUAL predictions, not opinions or observations
- A prediction must be falsifiable — something that can be confirmed or invalidated by future events
- Timelines should be specific when the text supports it (Q3 2026, by end of year, within 6 months)
- Conviction is the author's implied confidence (0.0 = throwaway speculation, 1.0 = near-certain)
- Framework references link to named evolving mental models (e.g. "Currency Stack", "Digital Industrialization", "Sats Flow")
- If no predictions exist in the note, return an empty predictions array — don't force it
- Domain should match the topic vocabulary: fed_policy, labor_market, fiscal_policy, geopolitics, bitcoin, credit_markets, energy, currencies, inflation, financial_plumbing, regulatory, demographics, technology, bitcoin_monetary, political_cycles, technology_sovereignty

Respond with JSON only."""

EXTRACTION_USER = """## Note to Extract

**Title:** {title}
**Topic:** {topic}
**Conviction Tier:** {conviction_tier}
**Body:**
{body}

## Existing Frameworks
{frameworks}

## Output Schema

```json
{{
  "predictions": [
    {{
      "claim": "specific falsifiable statement",
      "measurable_outcome": "how to verify this — what would confirm or invalidate it",
      "timeline": "natural language timeline (e.g. 'Q3 2026', 'by year-end', '6-12 months')",
      "conviction": 0.7,
      "conviction_reasoning": "why this confidence level — hedge words, qualifiers, strength of argument",
      "domain": "topic_from_vocabulary"
    }}
  ],
  "framework_references": [
    {{
      "framework_name": "exact name of existing framework OR 'new: Short Description'",
      "relation": "defines|extends|challenges|applies|evolves",
      "context": "why this note relates to this framework"
    }}
  ]
}}
```"""