"""
Ten31 Thoughts - First Principles Evaluator
Evaluates every incoming framework against the classical reference library.
This REPLACES empirical/track-record scoring as the primary ranking signal.

The question is not "did this person predict correctly?" but
"does this framework align with or violate principles about human nature,
political economy, and monetary history that have been validated over millennia?"
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import ExternalFramework, ContentItem, gen_id
from ..llm.router import LLMRouter
from .classical_reference import (
    CLASSICAL_DOMAINS, ALL_PRINCIPLES,
    get_principles_for_topic, format_principles_for_llm,
    TOPIC_TO_DOMAINS,
)
from ..llm.date_context import get_date_context

logger = logging.getLogger(__name__)

_DATE_CTX = get_date_context()

EVALUATION_SYSTEM = _DATE_CTX + """You are a classically trained macro analyst. Your role is to evaluate
analytical frameworks against FIRST PRINCIPLES drawn from the Western intellectual tradition:
sound money theory, political cycle analysis, the study of human nature and incentives,
and the foundations of property rights and rule of law.

You are NOT evaluating whether a framework "works" in the short term or whether it
predicted recent market moves correctly. You are evaluating whether the UNDERLYING LOGIC
is grounded in timeless principles about how the world actually works.

A framework that predicts well but violates first principles is a trade that hasn't
blown up yet. A framework that aligns with first principles but hasn't played out on
the current timeline may simply require patience.

For the framework presented, evaluate it against each relevant principle:

1. For each principle, determine: ALIGNS, VIOLATES, or NEUTRAL
2. If VIOLATES, identify the specific violation signal and explain the tension
3. If ALIGNS, explain how the framework's logic connects to the principle
4. Provide an overall first_principles_score from 0.0 to 1.0:
   - 1.0 = Deeply grounded in classical principles, reasoning from fundamentals
   - 0.7 = Generally aligned, minor blind spots
   - 0.5 = Mixed — some sound reasoning alongside unexamined assumptions
   - 0.3 = Significant violations of first principles, relies on assumptions
           that historical experience contradicts
   - 0.0 = Directly contradicts fundamental axioms about human nature,
           money, or political economy

5. Provide a classical_insight: What would the source thinkers say about this framework?
   Reference specific thinkers and works. Not as decoration — as genuine intellectual engagement.

6. Provide a grounding_assessment: Is this framework reasoning from first principles
   or from recent data patterns? Data patterns shift; principles don't.

Respond ONLY with a JSON object. No preamble."""


EVALUATION_USER = """Evaluate this framework against first principles:

FRAMEWORK: {framework_name}
GUEST: {guest_name}
DESCRIPTION: {description}
CAUSAL CHAIN: {causal_chain}
TIME HORIZON: {time_horizon}

RELEVANT FIRST PRINCIPLES TO EVALUATE AGAINST:

{principles}

How well does this framework's underlying logic hold up against these
timeless principles about money, governance, human nature, and property?"""


class FirstPrinciplesEvaluator:
    """
    Evaluates frameworks against the classical reference library.
    Produces a first_principles_score that REPLACES empirical scoring
    as the primary signal for framework ranking.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def evaluate_framework(self, framework: ExternalFramework) -> dict:
        """
        Evaluate a single framework against relevant first principles.
        Updates the framework's scoring fields and returns the evaluation.
        """
        # Determine which principles are relevant based on the framework's content
        relevant_principles = self._get_relevant_principles(framework)

        if not relevant_principles:
            # If we can't determine relevance, use all principles
            relevant_principles = ALL_PRINCIPLES

        principles_text = format_principles_for_llm(relevant_principles)

        # Format causal chain
        causal_str = ""
        if framework.causal_chain:
            if isinstance(framework.causal_chain, dict):
                causal_str = "; ".join(f"{k}: {v}" for k, v in framework.causal_chain.items())
            else:
                causal_str = str(framework.causal_chain)

        prompt = EVALUATION_USER.format(
            framework_name=framework.framework_name,
            guest_name=framework.guest_name or "Unknown",
            description=framework.description,
            causal_chain=causal_str or "Not specified",
            time_horizon=framework.time_horizon or "Not specified",
            principles=principles_text,
        )

        try:
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system=EVALUATION_SYSTEM,
            )

            score = result.get("first_principles_score")
            if score is not None:
                score = max(0.0, min(1.0, float(score)))

            # Build evaluation record
            evaluation = {
                "first_principles_score": score,
                "classical_insight": result.get("classical_insight", ""),
                "grounding_assessment": result.get("grounding_assessment", ""),
                "principle_evaluations": result.get("principle_evaluations", []),
                "violations": [],
                "alignments": [],
            }

            # Extract violations and alignments
            for pe in result.get("principle_evaluations", result.get("evaluations", [])):
                if isinstance(pe, dict):
                    status = pe.get("status", pe.get("alignment", "")).lower()
                    if "violat" in status:
                        evaluation["violations"].append({
                            "principle_id": pe.get("principle_id", ""),
                            "explanation": pe.get("explanation", ""),
                        })
                    elif "align" in status:
                        evaluation["alignments"].append({
                            "principle_id": pe.get("principle_id", ""),
                            "explanation": pe.get("explanation", ""),
                        })

            # Store results on the framework
            # reasoning_score becomes the first_principles_score
            framework.reasoning_score = score
            framework.reasoning_notes = (
                f"First Principles Score: {score:.2f}\n"
                f"Classical Insight: {evaluation['classical_insight'][:500]}\n"
                f"Grounding: {evaluation['grounding_assessment'][:500]}\n"
                f"Violations: {len(evaluation['violations'])} | "
                f"Alignments: {len(evaluation['alignments'])}"
            )[:2000]

            self.session.flush()

            logger.info(
                f"First principles evaluation: {framework.framework_name} "
                f"-> {score:.2f} ({len(evaluation['violations'])} violations, "
                f"{len(evaluation['alignments'])} alignments)"
            )

            return evaluation

        except Exception as e:
            logger.error(f"First principles evaluation failed for {framework.framework_name}: {e}")
            return {"error": str(e), "first_principles_score": None}

    async def evaluate_thesis_element(self, claim_text: str, topic: str) -> dict:
        """
        Evaluate one of our own thesis elements against first principles.
        Used for self-examination — are we reasoning from principles or pattern-matching?
        """
        relevant = get_principles_for_topic(topic)
        if not relevant:
            relevant = ALL_PRINCIPLES[:6]

        principles_text = format_principles_for_llm(relevant)

        prompt = f"""Evaluate this thesis position against first principles:

POSITION: {claim_text}
TOPIC: {topic}

RELEVANT FIRST PRINCIPLES:

{principles_text}

Is this position reasoning from first principles, or from recent data patterns?"""

        try:
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system=EVALUATION_SYSTEM,
            )
            return result
        except Exception as e:
            logger.error(f"Thesis element evaluation failed: {e}")
            return {"error": str(e)}

    def _get_relevant_principles(self, framework: ExternalFramework) -> list[dict]:
        """Determine which principles are relevant to a framework based on its content."""
        text = f"{framework.framework_name} {framework.description}".lower()

        # Map keywords to domains
        domain_keywords = {
            "sound_money": ["money", "currency", "dollar", "inflation", "fed", "rate",
                           "credit", "debt", "monetary", "debasement", "printing",
                           "qe", "balance sheet", "bitcoin", "gold", "store of value"],
            "political_cycles": ["government", "fiscal", "deficit", "political", "election",
                                "regulation", "empire", "decline", "democracy", "populis",
                                "tariff", "industrial policy", "subsidy"],
            "human_nature": ["incentive", "behavior", "labor", "employment", "consumer",
                            "data", "statistic", "revision", "manipulation", "forward guidance",
                            "central plan", "manage", "control", "soft landing"],
            "property_rights": ["property", "confiscat", "tax", "regulation", "rule of law",
                               "jurisdiction", "capital flow", "sanction", "freeze",
                               "surveillance", "privacy", "cbdc"],
        }

        relevant_domains = set()
        for domain, keywords in domain_keywords.items():
            for kw in keywords:
                if kw in text:
                    relevant_domains.add(domain)
                    break

        if not relevant_domains:
            relevant_domains = {"sound_money", "human_nature"}

        return [p for p in ALL_PRINCIPLES if p["domain"] in relevant_domains]
