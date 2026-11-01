"""Selectable writing options. Single source of truth for forms, validation and prompts."""
from __future__ import annotations

MAX_PROMPT_CHARS = 2000

# (key, label, instruction used when building the AI prompt)
WRITING_TYPES = (
    ("general", "General writing", "Write clear, well-structured general-purpose text."),
    ("email", "Email", "Write a complete email with a subject line, greeting, body and sign-off."),
    ("social", "Social media post", "Write an engaging social media post. Hashtags are welcome where natural."),
    ("product", "Product description", "Write a compelling product description that highlights benefits."),
    ("blog_intro", "Blog introduction", "Write a hook-driven introduction for a blog article."),
    ("blog_post", "Blog post", "Write a full blog post with a title, short sections and a conclusion."),
    ("ad", "Advertisement", "Write persuasive advertisement copy with a clear call to action."),
    ("website", "Website copy", "Write website copy with a headline, supporting text and a call to action."),
    ("seo_meta", "SEO meta description", "Write an SEO meta description of at most 160 characters, whatever the requested length."),
)

# (key, label, instruction)
LANGUAGES = (
    ("english", "English", "Write in English."),
    ("urdu", "Urdu", "Write in Urdu using Urdu script."),
    ("roman_urdu", "Roman Urdu", "Write in Roman Urdu: Urdu written with the Latin alphabet, not Urdu script."),
    ("spanish", "Spanish", "Write in Spanish."),
    ("french", "French", "Write in French."),
    ("german", "German", "Write in German."),
    ("arabic", "Arabic", "Write in Arabic using Arabic script."),
    ("hindi", "Hindi", "Write in Hindi using Devanagari script."),
)

TONES = (
    ("professional", "Professional"),
    ("friendly", "Friendly"),
    ("persuasive", "Persuasive"),
    ("casual", "Casual"),
    ("creative", "Creative"),
    ("formal", "Formal"),
)

# (key, label, target size, max_tokens)
LENGTHS = (
    ("short", "Short", "about 50 to 100 words", 400),
    ("medium", "Medium", "about 150 to 300 words", 900),
    ("long", "Long", "about 500 to 800 words", 1800),
)

DEFAULT_FORM = {
    "prompt": "",
    "writing_type": "general",
    "output_language": "english",
    "tone": "professional",
    "length": "medium",
}


def pairs(options):
    """Return [(key, label), ...] for use in <select> elements."""
    return [(o[0], o[1]) for o in options]


def keys(options):
    return {o[0] for o in options}


def label_for(options, key):
    for option in options:
        if option[0] == key:
            return option[1]
    return key


def lookup(options, key):
    for option in options:
        if option[0] == key:
            return option
    raise KeyError(key)
