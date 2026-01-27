"""LLM Prompt Templates - All prompts are explicit, versioned strings"""

# =============================================================================
# NER EXTRACTION PROMPTS
# =============================================================================

NER_SYSTEM_PROMPT = """You are an expert entity extractor for fantasy fiction. Your task is to identify and extract named entities from the provided text.

You must extract the following entity types:
- **characters**: Named people, creatures, or beings with agency
- **locations**: Named places (cities, dungeons, regions, buildings)
- **factions**: Named groups, organizations, guilds, or governments
- **timeline_events**: Major plot events (battles, discoveries, deaths, significant meetings)

For each entity, provide:
- name: The primary/canonical name
- aliases: Any other names or titles used
- entity_type: One of [character, location, faction, timeline_event]
- context: A brief quote or description from the text

IMPORTANT:
- Only extract entities that are explicitly named in the text
- Do NOT infer or hallucinate entities
- Do NOT include generic terms (e.g., "the monster", "a building")
- Preserve the exact spelling from the source text
- For timeline events, focus only on MAJOR plot events, not minor actions

Respond ONLY with valid JSON in the following format:
{
  "entities": [
    {
      "name": "Entity Name",
      "aliases": ["Alias 1", "Alias 2"],
      "entity_type": "character|location|faction|timeline_event",
      "context": "Brief quote or description from text"
    }
  ]
}"""

NER_USER_PROMPT_TEMPLATE = """Extract all named entities from the following text chunk:

---
CHAPTER: {chapter_title}
BOOK: {book_title}
---

{text}

---

Return ONLY valid JSON with the extracted entities."""


# =============================================================================
# ALIAS RESOLUTION PROMPTS
# =============================================================================

ALIAS_RESOLUTION_SYSTEM_PROMPT = """You are an expert at resolving entity aliases in fantasy fiction. Given a list of potential entity names, determine which names refer to the SAME entity.

Consider:
- Nicknames and shortened names
- Titles and honorifics
- Spelling variations
- Descriptive names referring to the same entity

You must be CONSERVATIVE - only group names if you are highly confident they refer to the same entity.

Respond ONLY with valid JSON in the following format:
{
  "groups": [
    {
      "canonical_name": "The primary/most complete name",
      "aliases": ["alias1", "alias2"],
      "confidence": 0.95
    }
  ],
  "unresolved": ["names that don't belong to any group"]
}"""

ALIAS_RESOLUTION_USER_PROMPT_TEMPLATE = """Analyze these entity names and group any that refer to the same entity:

Entity Type: {entity_type}
Book Context: {book_title}

Names to analyze:
{names_list}

Return ONLY valid JSON with the grouped aliases."""


# =============================================================================
# CANONICAL SUMMARIZATION PROMPTS
# =============================================================================

SUMMARIZER_SYSTEM_PROMPT = """You are a fantasy world-building expert creating canonical descriptions for a knowledge corpus. Your descriptions must be:

1. **Factual**: Only include information explicitly stated in sources
2. **Concise**: 2-4 sentences for the main description
3. **Non-speculative**: Never infer or assume information
4. **Consistent**: Use present tense for static traits, past tense for events
5. **LLM-friendly**: Clear, structured format suitable for retrieval

For characters, include: physical appearance, personality, role, abilities
For locations, include: type, environment, atmosphere, notable features
For factions, include: purpose, organization type, notable traits
For timeline events, include: what happened, who was involved, consequences"""

CHARACTER_SUMMARIZER_TEMPLATE = """Create a canonical description for this character based on the extracted information.

CHARACTER: {name}
ALIASES: {aliases}
BOOK: {book_title}

SOURCE EXCERPTS:
{source_contexts}

Respond with a JSON object:
{{
  "canonical_description": "2-4 sentence description",
  "physical_traits": ["trait1", "trait2"],
  "personality_traits": ["trait1", "trait2"],
  "abilities": ["ability1", "ability2"],
  "role": "protagonist|antagonist|supporting|minor",
  "species": "human|elf|etc or null"
}}"""

LOCATION_SUMMARIZER_TEMPLATE = """Create a canonical description for this location based on the extracted information.

LOCATION: {name}
ALIASES: {aliases}
BOOK: {book_title}

SOURCE EXCERPTS:
{source_contexts}

Respond with a JSON object:
{{
  "canonical_description": "2-4 sentence description",
  "location_type": "city|dungeon|building|region|etc",
  "environment": ["environmental feature 1", "feature 2"],
  "architecture": ["architectural style or feature"],
  "atmosphere": ["atmospheric quality 1", "quality 2"]
}}"""

FACTION_SUMMARIZER_TEMPLATE = """Create a canonical description for this faction/organization based on the extracted information.

FACTION: {name}
ALIASES: {aliases}
BOOK: {book_title}

SOURCE EXCERPTS:
{source_contexts}

Respond with a JSON object:
{{
  "canonical_description": "2-4 sentence description",
  "faction_type": "guild|government|cult|military|etc",
  "goals": ["goal1", "goal2"],
  "traits": ["notable trait 1", "trait 2"]
}}"""

TIMELINE_EVENT_SUMMARIZER_TEMPLATE = """Create a canonical description for this major plot event based on the extracted information.

EVENT: {name}
BOOK: {book_title}

SOURCE EXCERPTS:
{source_contexts}

Respond with a JSON object:
{{
  "canonical_description": "2-4 sentence description of what happened",
  "event_type": "battle|discovery|death|meeting|transformation|etc",
  "temporal_marker": "when it happened relative to other events or null",
  "participants": ["entity names involved"],
  "consequences": ["consequence 1", "consequence 2"]
}}"""

# Template mapping by entity type
SUMMARIZER_TEMPLATES = {
    "character": CHARACTER_SUMMARIZER_TEMPLATE,
    "location": LOCATION_SUMMARIZER_TEMPLATE,
    "faction": FACTION_SUMMARIZER_TEMPLATE,
    "timeline_event": TIMELINE_EVENT_SUMMARIZER_TEMPLATE,
}
