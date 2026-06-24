"""
Protection Filters for Jaya AI
Provides functions to sanitize outbound requests and filter inbound responses.
"""

import re
from typing import List

# Example list of disallowed patterns (can be extended)
DISALLOWED_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(bomb|explosive|weapon|kill|murder|terror)\b", re.I),
    re.compile(r"\b(hack|exploit|virus|malware|ransomware)\b", re.I),
    re.compile(r"\b(self.?harm|suicide|cut)\b", re.I),
    # Add more as needed
]

# Whitelist of allowed domains for internet fallback (example)
ALLOWED_DOMAINS: List[str] = [
    "wikipedia.org",
    "duckduckgo.com",
    "api.allorigins.win",  # for CORS proxy if needed
    # Add your own trusted domains
]

def sanitize_outbound(text: str) -> str:
    """
    Sanitize user input before sending it to an external service.
    - Removes or redacts potentially dangerous content.
    - Optionally, can replace with safe placeholders.
    Returns a safe version of the input.
    """
    # For now, we just check and if disallowed, we return a safe placeholder.
    for pattern in DISALLOWED_PATTERNS:
        if pattern.search(text):
            # Replace the matched part with [REDACTED]
            text = pattern.sub("[REDACTED]", text)
    # Additionally, we could limit length to avoid overly long queries
    if len(text) > 200:
        text = text[:200] + "..."
    return text

def filter_inbound(text: str) -> str:
    """
    Filter content received from an external source before presenting to the user.
    - Removes any disallowed content that might have slipped through.
    - Could also strip HTML, scripts, etc.
    Returns safe text.
    """
    # Remove any HTML tags (simple regex)
    text = re.sub(r"<[^>]+>", "", text)
    # Check for disallowed patterns
    for pattern in DISALLOWED_PATTERNS:
        if pattern.search(text):
            # If found, we might want to return a safe message instead
            return "Maaf, saya tidak dapat menampilkan konten tersebut karena tidak sesuai dengan pedoman keamanan."
    return text

def is_domain_allowed(url: str) -> bool:
    """
    Check if the URL's domain is in the allowed list.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove port if present
        domain = domain.split(":")[0]
        return any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_DOMAINS)
    except Exception:
        return False