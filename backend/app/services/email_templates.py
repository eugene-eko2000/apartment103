"""Loads and renders the guest-facing email templates under backend/data/.

One directory per supported language (matching app.models.guest.Language:
en/de/fr/it), each holding the same set of template files (currently
booking_confirmation.html and scheduled_payment.html). Every template file
starts with a `Subject: ...` line — itself a Jinja expression — followed by
a blank line and then the HTML body, so a single file carries both. This
keeps every guest-facing string, in every language, inside data/ rather
than in Python: translating or wording-tweaking an email never touches
this module.
"""

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template

from app.models.guest import Language

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Keep in sync with app.models.guest.Language.
_SUPPORTED_LANGUAGES: tuple[Language, ...] = ("en", "de", "fr", "it")
_DEFAULT_LANGUAGE: Language = "en"


def _money(amount: float, currency: str) -> str:
    return f"{amount:,.2f} {currency}"


def _percent(fraction: float) -> str:
    return f"{fraction * 100:.0f}"


_env = Environment(
    loader=FileSystemLoader(DATA_DIR),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["money"] = _money
_env.filters["percent"] = _percent


def resolve_language(preferred: Language | None) -> Language:
    return preferred if preferred in _SUPPORTED_LANGUAGES else _DEFAULT_LANGUAGE


@lru_cache(maxsize=None)
def _compiled_templates(language: Language, name: str) -> tuple[Template, Template]:
    """(subject_template, body_template) for data/<language>/<name>. Reads
    and compiles once per (language, name) — template files don't change at
    runtime, so re-parsing on every email would be pure waste."""
    raw = (DATA_DIR / language / name).read_text(encoding="utf-8")
    subject_source, separator, body_source = raw.partition("\n\n")
    if not separator or not subject_source.startswith("Subject: "):
        raise ValueError(f"Template {language}/{name} must start with a 'Subject: ...' line, then a blank line")
    return _env.from_string(subject_source.removeprefix("Subject: ")), _env.from_string(body_source)


def render_email(*, language: Language | None, name: str, context: dict) -> tuple[str, str]:
    """Render data/<resolved language>/<name> with `context`. Falls back to
    `_DEFAULT_LANGUAGE` when the guest has no (or an unsupported) preferred
    language. Returns (subject, html_body)."""
    subject_template, body_template = _compiled_templates(resolve_language(language), name)
    return subject_template.render(**context), body_template.render(**context)
