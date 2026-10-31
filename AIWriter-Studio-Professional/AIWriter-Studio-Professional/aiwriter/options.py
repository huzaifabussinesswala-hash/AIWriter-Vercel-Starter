"""Selectable writing options. Single source of truth for forms, validation and prompts."""
from __future__ import annotations

MAX_PROMPT_CHARS = 2000

# (key, label, instruction used when building the AI prompt)
WRITING_TYPES = (
    ("general", "General writing", "Write clear, well-structured, useful general-purpose text."),
    ("email", "Professional email", "Write a complete email with a relevant subject line, greeting, concise body, and appropriate sign-off."),
    ("social", "Social media post", "Write an engaging platform-ready social post with a strong opening, concise value, and natural call to action. Add relevant hashtags only when useful."),
    ("product", "E-commerce product description", "Write persuasive, benefit-led product copy. Include a clear product title, key features, customer benefits, and a natural call to action. Never invent specifications."),
    ("blog_intro", "Blog introduction", "Write a compelling blog introduction with a reader-focused hook, context, and a clear promise of what the article will cover."),
    ("blog_post", "Long-form blog article", "Write a complete, original, useful blog article with an engaging title, introduction, logical H2/H3-style section headings, practical details, and a conclusion. Avoid padding and repetition."),
    ("seo_article", "SEO-optimized article", "Write a helpful search-focused article that naturally addresses the primary topic and search intent. Use a compelling title, descriptive section headings, semantic related terms naturally, concise paragraphs, FAQ section when relevant, and a useful conclusion. Do not keyword-stuff or claim guaranteed rankings."),
    ("seo_meta", "SEO title and meta description", "Create an SEO title and meta description. Keep the meta description within approximately 150-160 characters. Provide a suggested URL slug and primary keyword when appropriate."),
    ("seo_outline", "SEO content brief / outline", "Create a search-intent-led content brief with target audience, search intent, suggested title, primary topic, related subtopics, structured H2/H3 outline, FAQs, and content angle. Do not invent search-volume data."),
    ("ad", "Advertisement copy", "Write persuasive ad variations with a clear audience, benefit-led hook, proof only when supplied, and a specific call to action. Avoid unsupported claims."),
    ("landing_page", "Landing page copy", "Write conversion-focused landing page copy with hero headline, subheadline, benefits, feature sections, objection handling, trust elements only when provided, and clear calls to action."),
    ("sales_email", "Sales email sequence", "Write a concise, personalized sales email or sequence with a relevant subject, customer problem, value proposition, and respectful call to action. Avoid spammy claims."),
    ("website", "Website copy", "Write clear website copy with a strong headline, supporting text, audience-specific benefits, and a clear call to action."),
    ("brand_story", "Brand story / about page", "Write an authentic brand story that explains purpose, audience, values, and differentiation. Do not invent company history or achievements."),
    ("video_script", "Video / YouTube script", "Write a spoken-word-friendly script with a strong opening hook, clear segments, transitions, and a closing call to action."),
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
