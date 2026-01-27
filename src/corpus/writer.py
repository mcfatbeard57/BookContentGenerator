"""Corpus Writer - Generate Markdown files with YAML front-matter"""
from pathlib import Path

from ruamel.yaml import YAML

from src.config import ENTITY_DIRS
from src.models.entities import (
    Character,
    Entity,
    Faction,
    Location,
    TimelineEvent,
)


# Configure YAML for round-trip safe output
yaml = YAML()
yaml.default_flow_style = False
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def entity_to_frontmatter(entity: Entity) -> dict:
    """Convert entity to YAML front-matter dictionary"""
    # Base fields for all entities
    frontmatter = {
        "entity_type": entity.entity_type,
        "entity_id": entity.entity_id,
        "name": entity.name,
        "aliases": entity.aliases if entity.aliases else [],
        "sources": [
            {
                "source_type": s.source_type,
                "source_id": s.source_id,
            }
            for s in entity.sources
        ],
        "first_appearance": entity.first_appearance,
        "occurrence_count": entity.occurrence_count,
        "last_updated": entity.last_updated.isoformat(),
    }
    
    return frontmatter


def entity_to_markdown_body(entity: Entity) -> str:
    """Convert entity to Markdown body content"""
    lines = []
    
    # Canonical description
    lines.append("## Canonical Description")
    lines.append("")
    if entity.canonical_description:
        lines.append(entity.canonical_description)
    else:
        lines.append("*No canonical description available.*")
    lines.append("")
    
    # Type-specific sections
    if isinstance(entity, Character):
        if entity.physical_traits:
            lines.append("## Physical Traits")
            lines.append("")
            for trait in entity.physical_traits:
                lines.append(f"- {trait}")
            lines.append("")
        
        if entity.personality_traits:
            lines.append("## Personality")
            lines.append("")
            for trait in entity.personality_traits:
                lines.append(f"- {trait}")
            lines.append("")
        
        if entity.abilities:
            lines.append("## Abilities")
            lines.append("")
            for ability in entity.abilities:
                lines.append(f"- {ability}")
            lines.append("")
        
        if entity.role:
            lines.append("## Role")
            lines.append("")
            lines.append(entity.role)
            lines.append("")
        
        if entity.species:
            lines.append("## Species")
            lines.append("")
            lines.append(entity.species)
            lines.append("")
    
    elif isinstance(entity, Location):
        if entity.location_type:
            lines.append("## Location Type")
            lines.append("")
            lines.append(entity.location_type)
            lines.append("")
        
        if entity.environment:
            lines.append("## Environment")
            lines.append("")
            for env in entity.environment:
                lines.append(f"- {env}")
            lines.append("")
        
        if entity.architecture:
            lines.append("## Architecture")
            lines.append("")
            for arch in entity.architecture:
                lines.append(f"- {arch}")
            lines.append("")
        
        if entity.atmosphere:
            lines.append("## Atmosphere")
            lines.append("")
            for atm in entity.atmosphere:
                lines.append(f"- {atm}")
            lines.append("")
    
    elif isinstance(entity, Faction):
        if entity.faction_type:
            lines.append("## Faction Type")
            lines.append("")
            lines.append(entity.faction_type)
            lines.append("")
        
        if entity.goals:
            lines.append("## Goals")
            lines.append("")
            for goal in entity.goals:
                lines.append(f"- {goal}")
            lines.append("")
        
        if entity.traits:
            lines.append("## Traits")
            lines.append("")
            for trait in entity.traits:
                lines.append(f"- {trait}")
            lines.append("")
    
    elif isinstance(entity, TimelineEvent):
        if entity.event_type:
            lines.append("## Event Type")
            lines.append("")
            lines.append(entity.event_type)
            lines.append("")
        
        if entity.temporal_marker:
            lines.append("## When")
            lines.append("")
            lines.append(entity.temporal_marker)
            lines.append("")
        
        if entity.participants:
            lines.append("## Participants")
            lines.append("")
            for participant in entity.participants:
                lines.append(f"- {participant}")
            lines.append("")
        
        if entity.consequences:
            lines.append("## Consequences")
            lines.append("")
            for consequence in entity.consequences:
                lines.append(f"- {consequence}")
            lines.append("")
    
    return "\n".join(lines)


def entity_to_file_content(entity: Entity) -> str:
    """Convert entity to complete file content with YAML front-matter"""
    import io
    
    # Generate YAML front-matter
    frontmatter = entity_to_frontmatter(entity)
    
    # Write YAML to string
    stream = io.StringIO()
    yaml.dump(frontmatter, stream)
    yaml_str = stream.getvalue()
    
    # Generate Markdown body
    body = entity_to_markdown_body(entity)
    
    # Combine with delimiters
    return f"---\n{yaml_str}---\n\n{body}"


def entity_to_filename(entity: Entity) -> str:
    """Generate filename for entity"""
    # Use entity_id but remove prefix
    name_part = entity.entity_id.split("_", 1)[1] if "_" in entity.entity_id else entity.entity_id
    return f"{name_part}.md"


def write_entity(entity: Entity, output_dir: Path | None = None) -> Path:
    """
    Write a single entity to its Markdown file.
    
    Returns the path to the written file.
    """
    # Determine output directory
    if output_dir is None:
        output_dir = ENTITY_DIRS.get(entity.entity_type)
        if output_dir is None:
            raise ValueError(f"No output directory configured for entity type: {entity.entity_type}")
    
    # Ensure directory exists
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate file path
    filename = entity_to_filename(entity)
    file_path = output_dir / filename
    
    # Generate content
    content = entity_to_file_content(entity)
    
    # Write file
    file_path.write_text(content, encoding="utf-8")
    
    return file_path


def write_all_entities(entities: list[Entity]) -> list[Path]:
    """
    Write all entities to their respective directories.
    
    Returns list of paths to written files.
    """
    written_paths: list[Path] = []
    
    print(f"Writing {len(entities)} entities to corpus...")
    
    for entity in entities:
        try:
            path = write_entity(entity)
            written_paths.append(path)
        except Exception as e:
            print(f"Warning: Failed to write entity {entity.entity_id}: {e}")
    
    print(f"  → Wrote {len(written_paths)} entity files")
    
    return written_paths
