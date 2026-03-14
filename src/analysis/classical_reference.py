"""
Ten31 Thoughts - Classical Reference Library
First principles from the intellectual tradition that formed Western thought,
organized by domain. Each principle is traced to source thinkers and articulated
as a testable axiom that incoming macro frameworks can be evaluated against.

This is NOT decorative — these principles function as the evaluation spine.
Every framework that enters the system gets measured against these axioms.
"""

# ═══════════════════════════════════════════════════════════════
# DOMAIN 1: SOUND MONEY & MONETARY DEBASEMENT
# Evaluates: Fed policy, inflation, currencies, bitcoin, credit
# ═══════════════════════════════════════════════════════════════

SOUND_MONEY = {
    "domain": "sound_money",
    "title": "Sound Money & Monetary Debasement",
    "applies_to": ["fed_policy", "inflation", "currencies", "bitcoin", "credit_markets", "financial_plumbing"],
    "principles": [
        {
            "id": "sm_01",
            "axiom": "Money must emerge from the market as a commodity with independent use-value before it can function as a medium of exchange. Imposed money without organic demand degrades over time.",
            "source_thinkers": ["Aristotle (Politics, Nicomachean Ethics)", "Carl Menger (On the Origins of Money)", "Ludwig von Mises (The Theory of Money and Credit)"],
            "implication": "Any framework assuming fiat currency stability as a baseline, rather than treating debasement as the default trajectory, inverts the historical record.",
            "violation_signals": [
                "Assumes the purchasing power of the dollar is stable or mean-reverting",
                "Treats monetary expansion as costless stimulus rather than redistribution",
                "Ignores the Cantillon effect — who receives new money first",
            ],
        },
        {
            "id": "sm_02",
            "axiom": "Debasement of the currency is the oldest and most universal fiscal strategy of governments under financial stress. It is not a modern invention; it is the default behavior of states.",
            "source_thinkers": ["Nicolaus Copernicus (Monetae Cudendae Ratio, 1526)", "Nicole Oresme (De Moneta, 1360)", "Ibn Khaldun (Muqaddimah)"],
            "implication": "When evaluating whether a government will inflate, debase, or restructure, the prior should be 'yes' unless extraordinary institutional constraints prevent it.",
            "violation_signals": [
                "Assumes governments will voluntarily choose austerity over inflation",
                "Treats debt sustainability as a solved problem through 'growth'",
                "Ignores that every fiat currency in history has lost most of its value",
            ],
        },
        {
            "id": "sm_03",
            "axiom": "Gresham's Law: bad money drives out good when exchange rates are fixed by law. People hoard sound money and spend debased money.",
            "source_thinkers": ["Thomas Gresham", "Aristophanes (The Frogs — earliest literary reference)", "Copernicus"],
            "implication": "When a monetary system contains both sound and unsound elements, rational actors will always migrate savings toward the sounder asset. This explains gold hoarding, bitcoin accumulation, and capital flight.",
            "violation_signals": [
                "Assumes people are indifferent between holding dollars and harder assets",
                "Treats capital flows as purely speculative rather than driven by monetary quality",
            ],
        },
        {
            "id": "sm_04",
            "axiom": "Credit expansion untethered from real savings creates an artificial boom that must eventually correct. The boom is the disease; the bust is the cure.",
            "source_thinkers": ["Richard Cantillon (Essai sur la Nature du Commerce)", "Ludwig von Mises (Human Action)", "Friedrich Hayek (Prices and Production)"],
            "implication": "Frameworks that assume credit-driven growth is sustainable, or that central banks can perpetually smooth the business cycle, violate the Austrian insight that malinvestment must liquidate.",
            "violation_signals": [
                "Assumes central bank intervention can permanently prevent recessions",
                "Treats low rates as neutral rather than distortionary",
                "Ignores the difference between credit expansion and genuine saving",
            ],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════
# DOMAIN 2: POLITICAL CYCLES & REPUBLIC DECAY
# Evaluates: fiscal policy, geopolitics, regulatory, demographics
# ═══════════════════════════════════════════════════════════════

POLITICAL_CYCLES = {
    "domain": "political_cycles",
    "title": "Political Cycles & Republic Decay",
    "applies_to": ["fiscal_policy", "geopolitics", "regulatory", "demographics"],
    "principles": [
        {
            "id": "pc_01",
            "axiom": "Polybius's Anacyclosis: governments cycle through monarchy → aristocracy → democracy → ochlocracy (mob rule) → tyranny → back to monarchy. The cycle is driven by the moral decay of each ruling class.",
            "source_thinkers": ["Polybius (Histories, Book VI)", "Aristotle (Politics)", "Plato (Republic, Book VIII)"],
            "implication": "Frameworks that assume democratic institutions are permanently stable, or that the current political order is the endpoint of governance, ignore 2,500 years of cyclical evidence.",
            "violation_signals": [
                "Assumes institutional stability as a baseline rather than something that must be actively maintained",
                "Treats current democratic norms as permanent rather than cyclical",
                "Ignores the pattern of elite capture followed by populist backlash",
            ],
        },
        {
            "id": "pc_02",
            "axiom": "Republics decay when the ruling class prioritizes private interest over public duty, and when the citizenry trades liberty for material comfort.",
            "source_thinkers": ["Cicero (De Re Publica)", "Sallust (Bellum Catilinae)", "Machiavelli (Discourses on Livy)"],
            "implication": "The expansion of government spending, entitlement programs, and corporate subsidy is not ideological — it follows a structural pattern of late-republic decay that has repeated across civilizations.",
            "violation_signals": [
                "Treats expanding government as a policy choice rather than a structural decay pattern",
                "Assumes fiscal discipline can be restored through elections alone",
                "Ignores the historical pattern of bread-and-circuses as a terminal phase indicator",
            ],
        },
        {
            "id": "pc_03",
            "axiom": "Empires overextend militarily and financially before they contract. The overextension is visible before the collapse, but denial is the default response of those inside the system.",
            "source_thinkers": ["Edward Gibbon (Decline and Fall of the Roman Empire)", "Paul Kennedy (Rise and Fall of the Great Powers)", "Sir John Glubb (The Fate of Empires)"],
            "implication": "Frameworks that assume American hegemony is permanent, or that the current global security architecture will persist unchanged, ignore every historical precedent of imperial overextension.",
            "violation_signals": [
                "Assumes the US can sustain both global military dominance and domestic entitlement spending indefinitely",
                "Treats the dollar's reserve currency status as permanent",
                "Ignores the fiscal math of simultaneous military + welfare commitments",
            ],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════
# DOMAIN 3: HUMAN NATURE & INCENTIVES
# Evaluates: labor market, consumer, positioning, data integrity
# ═══════════════════════════════════════════════════════════════

HUMAN_NATURE = {
    "domain": "human_nature",
    "title": "Human Nature & Incentives",
    "applies_to": ["labor_market", "inflation", "fiscal_policy", "energy", "regulatory", "financial_plumbing"],
    "principles": [
        {
            "id": "hn_01",
            "axiom": "People respond to incentives — always. When you subsidize something, you get more of it. When you tax something, you get less. Unintended consequences are not accidental; they are the predictable result of ignoring second-order effects.",
            "source_thinkers": ["Adam Smith (Wealth of Nations)", "Frederic Bastiat (That Which Is Seen and That Which Is Not Seen)", "Thomas Sowell (Basic Economics)"],
            "implication": "Any framework that evaluates policy by its stated intention rather than its incentive structure will systematically mispredict outcomes. Always ask: what behavior does this incentivize?",
            "violation_signals": [
                "Evaluates policy by stated goals rather than incentive effects",
                "Ignores second-order consequences of interventions",
                "Assumes people will behave as policymakers intend rather than as incentives dictate",
            ],
        },
        {
            "id": "hn_02",
            "axiom": "Thucydides's triad: nations act from fear, honor, and interest. These three motivations explain nearly all geopolitical behavior, and they have not changed in 2,500 years.",
            "source_thinkers": ["Thucydides (History of the Peloponnesian War)", "Hans Morgenthau (Politics Among Nations)", "Henry Kissinger (Diplomacy)"],
            "implication": "Geopolitical analysis that relies on 'rational actor' models or assumes nations will cooperate because it's mutually beneficial ignores that honor and fear regularly override material interest.",
            "violation_signals": [
                "Assumes rational economic interest will prevent military conflict",
                "Ignores the role of national honor and status anxiety in decision-making",
                "Treats international relations as a coordination game rather than a competitive one",
            ],
        },
        {
            "id": "hn_03",
            "axiom": "No man can be trusted to measure himself honestly. Institutions that self-report their own performance will systematically flatter the data.",
            "source_thinkers": ["David Hume (political maxim: 'every man must be supposed a knave')", "Public Choice Theory (Buchanan & Tullock)", "Goodhart's Law"],
            "implication": "Government economic statistics (payrolls, CPI, GDP) are produced by institutions with career incentives to present favorable numbers. Systematic positive bias in initial releases followed by downward revisions is not error — it is incentive-compatible behavior.",
            "violation_signals": [
                "Takes initial government data releases at face value",
                "Assumes statistical methodological changes are neutral improvements",
                "Ignores the pattern of systematic positive bias in preliminary data",
            ],
        },
        {
            "id": "hn_04",
            "axiom": "Knowledge is dispersed, not concentrated. No central planner can possess the information embedded in market prices. The pretense of knowledge is the most dangerous form of ignorance.",
            "source_thinkers": ["Friedrich Hayek (The Use of Knowledge in Society, 1945)", "Adam Smith (invisible hand)", "Leonard Read (I, Pencil)"],
            "implication": "Frameworks that assume central banks, regulators, or governments can successfully manage complex economic systems through top-down intervention violate the knowledge problem. The question is not whether the planner means well, but whether they can know enough.",
            "violation_signals": [
                "Assumes the Fed has sufficient information to optimally set interest rates",
                "Treats industrial policy as capable of picking winners",
                "Believes forward guidance can substitute for price discovery",
            ],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════
# DOMAIN 4: PROPERTY RIGHTS & RULE OF LAW
# Evaluates: regulatory, bitcoin, geopolitics, fiscal policy
# ═══════════════════════════════════════════════════════════════

PROPERTY_RIGHTS = {
    "domain": "property_rights",
    "title": "Property Rights & Rule of Law",
    "applies_to": ["regulatory", "bitcoin", "geopolitics", "fiscal_policy", "currencies"],
    "principles": [
        {
            "id": "pr_01",
            "axiom": "The security of property is the foundation of prosperity. Where property can be confiscated, debased, or arbitrarily taxed, capital will flee to safer jurisdictions or harder assets.",
            "source_thinkers": ["John Locke (Second Treatise of Government)", "Hernando de Soto (The Mystery of Capital)", "Douglass North (Institutions, Institutional Change)"],
            "implication": "Capital flows are not random — they follow the gradient of property rights security. Analyzing flows without understanding the institutional environment is like analyzing water flow without understanding gravity.",
            "violation_signals": [
                "Ignores the role of property rights security in capital allocation decisions",
                "Assumes capital will remain in jurisdictions that erode property protections",
                "Treats regulatory risk as a secondary consideration in investment frameworks",
            ],
        },
        {
            "id": "pr_02",
            "axiom": "The separation of powers exists to constrain the natural tendency of power to concentrate and corrupt. When these separations erode, the rule of law gives way to rule by law — the powerful writing rules that benefit themselves.",
            "source_thinkers": ["Montesquieu (The Spirit of the Laws)", "James Madison (Federalist No. 51)", "Lord Acton (power corrupts)"],
            "implication": "The erosion of institutional checks — regulatory agencies acting as both prosecutor and judge, executive overreach via emergency powers, the politicization of central banks — is not noise. It is signal about the structural trajectory of governance.",
            "violation_signals": [
                "Treats institutional independence (Fed, judiciary) as guaranteed rather than contested",
                "Ignores the concentration of regulatory power as a risk factor",
                "Assumes rule of law is static rather than actively contested",
            ],
        },
        {
            "id": "pr_03",
            "axiom": "Voluntary exchange creates wealth; coerced exchange destroys it. The degree to which an economy relies on voluntary vs. coerced transactions is the single best predictor of its long-term trajectory.",
            "source_thinkers": ["Adam Smith (Wealth of Nations)", "Bastiat (The Law)", "Milton Friedman (Capitalism and Freedom)"],
            "implication": "The growth of mandates, regulations, subsidies, and tariffs represents a shift from voluntary to coerced economic activity. This doesn't show up in GDP (which counts government spending as positive) but it shows up in productivity, innovation, and long-run growth.",
            "violation_signals": [
                "Treats government spending as equivalent to private investment in GDP",
                "Assumes regulation is costless or net-positive by default",
                "Ignores the deadweight loss of coerced transactions",
            ],
        },
    ],
}


# ═══════════════════════════════════════════════════════════════
# COMBINED REFERENCE: All domains accessible as a single structure
# ═══════════════════════════════════════════════════════════════

CLASSICAL_DOMAINS = [SOUND_MONEY, POLITICAL_CYCLES, HUMAN_NATURE, PROPERTY_RIGHTS]

# Flat list of all principles for iteration
ALL_PRINCIPLES = []
for domain in CLASSICAL_DOMAINS:
    for principle in domain["principles"]:
        ALL_PRINCIPLES.append({
            **principle,
            "domain": domain["domain"],
            "domain_title": domain["title"],
        })

# Map topics to relevant domains
TOPIC_TO_DOMAINS = {}
for domain in CLASSICAL_DOMAINS:
    for topic in domain["applies_to"]:
        if topic not in TOPIC_TO_DOMAINS:
            TOPIC_TO_DOMAINS[topic] = []
        TOPIC_TO_DOMAINS[topic].append(domain["domain"])


def get_principles_for_topic(topic: str) -> list[dict]:
    """Get all first principles relevant to a given macro topic."""
    domains = TOPIC_TO_DOMAINS.get(topic, [])
    return [p for p in ALL_PRINCIPLES if p["domain"] in domains]


def get_domain(domain_id: str) -> dict:
    """Get a domain by ID."""
    for d in CLASSICAL_DOMAINS:
        if d["domain"] == domain_id:
            return d
    return None


def format_principles_for_llm(principles: list[dict]) -> str:
    """Format principles into a string for LLM prompt context."""
    lines = []
    for p in principles:
        lines.append(f"[{p['id']}] {p['axiom']}")
        lines.append(f"  Source: {', '.join(p['source_thinkers'])}")
        lines.append(f"  Implication: {p['implication']}")
        lines.append(f"  Violation signals:")
        for v in p["violation_signals"]:
            lines.append(f"    - {v}")
        lines.append("")
    return "\n".join(lines)
