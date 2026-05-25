"""Versioned prompt loader."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def get_prompt(name: str, version: str = "v1", **kwargs: str) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        name: Template filename without .j2 extension.
        version: Prompt version directory (e.g., "v1", "v2").
        **kwargs: Template variables.

    Returns:
        Rendered prompt string.
    """
    base = Path(__file__).parent / version
    if not base.exists():
        raise ValueError(f"Prompt version directory not found: {base}")
    env = Environment(
        loader=FileSystemLoader(str(base)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(f"{name}.j2").render(**kwargs)
