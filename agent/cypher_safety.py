"""Validate LLM-generated Cypher before execution."""

import re

FORBIDDEN_PATTERN = re.compile(
    r"\b("
    r"CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|FOREACH|USE|"
    r"LOAD\s+CSV|CALL\s|APOC\.|DBMS\.|DB\.|GRANT|DENY|SHOW\s+"
    r")\b",
    re.IGNORECASE,
)

READ_QUERY_PATTERN = re.compile(
    r"\b(MATCH|OPTIONAL\s+MATCH|WITH|RETURN|UNWIND|WHERE|ORDER\s+BY|LIMIT|SKIP)\b",
    re.IGNORECASE,
)


def strip_markdown_fences(cypher: str) -> str:
    text = cypher.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def extract_single_query(cypher: str) -> str:
    """Keep only the first statement if the model returns multiple."""
    parts = [p.strip() for p in cypher.split(";") if p.strip()]
    return parts[0] if parts else ""


def mask_quoted_strings(cypher: str) -> str:
    """Replace quoted string literals with spaces so keyword scans ignore their contents."""
    masked: list[str] = []
    i = 0
    while i < len(cypher):
        ch = cypher[i]
        if ch in ('"', "'"):
            quote = ch
            start = i
            i += 1
            while i < len(cypher):
                if cypher[i] == "\\" and i + 1 < len(cypher):
                    i += 2
                    continue
                if cypher[i] == quote:
                    i += 1
                    break
                i += 1
            masked.append(" " * (i - start))
        else:
            masked.append(ch)
            i += 1
    return "".join(masked)


def validate_read_only_cypher(cypher: str) -> str:
    """Return cleaned Cypher or raise ValueError for unsafe/non-read queries."""
    cleaned = extract_single_query(strip_markdown_fences(cypher))
    if not cleaned:
        raise ValueError("Empty Cypher query")

    # Remove comments before keyword checks.
    no_line_comments = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)
    no_comments = re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)
    scan_target = mask_quoted_strings(no_comments)

    if FORBIDDEN_PATTERN.search(scan_target):
        match = FORBIDDEN_PATTERN.search(scan_target)
        raise ValueError(f"Forbidden Cypher operation detected: {match.group(0)}")

    if not READ_QUERY_PATTERN.search(scan_target):
        raise ValueError("Cypher must be a read-only query using MATCH/RETURN/WITH")

    return cleaned


def enforce_result_limit(cypher: str, default_limit: int = 100) -> str:
    """Append LIMIT if the query does not already bound result size."""
    if re.search(r"\bLIMIT\s+\d+\b", cypher, re.IGNORECASE):
        return cypher
    return f"{cypher.rstrip()}\nLIMIT {default_limit}"
