import datetime
import os
import re

_FORBIDDEN_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
_RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Connective words that Brazilian Portuguese name-capitalization conventions
# keep lowercase (unless they're the first word). Fixes baseline Known
# Issue #10: Python's str.title() turns "joão da silva" into
# "João Da Silva", which no Portuguese speaker would write by hand.
_PTBR_LOWERCASE_CONNECTIVES = {"de", "da", "do", "das", "dos", "e", "di", "du", "van", "von"}


def sanitize_filename(name: str) -> str:
    """Strip characters Windows forbids in filenames, then guard against
    the small set of reserved device names (CON, PRN, NUL, COM1..9,
    LPT1..9) that fail to create as a file regardless of extension."""
    cleaned = _FORBIDDEN_CHARS_RE.sub("_", name or "").strip().strip(".")
    if not cleaned:
        return "sem_nome"
    stem = cleaned.split(".")[0].upper()
    if stem in _RESERVED_WINDOWS_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def truncate_for_path_limits(directory: str, filename: str, max_total: int = 240) -> str:
    """
    Trim `filename` (keeping its extension) so that
    len(directory) + 1 + len(filename) stays under max_total.

    Guards against baseline Known Issue #8: a long event name + a long
    person's name + a deep folder can exceed Windows' historical
    MAX_PATH-adjacent limits and make doc.save() fail with no clear
    explanation to a non-technical user.
    """
    budget = max_total - len(directory) - 1
    if budget <= 0 or len(filename) <= budget:
        return filename
    base, ext = os.path.splitext(filename)
    keep = max(1, budget - len(ext))
    return base[:keep].rstrip() + ext


def format_cpf(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11:
        return f"{digits[0:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:11]}"
    return raw or ""


def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M")


def ensure_font_file(font_path: str) -> str:
    if not font_path or not os.path.isfile(font_path):
        raise FileNotFoundError("Escolha um arquivo de fonte .ttf ou .otf.")
    ext = os.path.splitext(font_path.lower())[1]
    if ext not in (".ttf", ".otf"):
        raise ValueError("A fonte deve ser .ttf ou .otf.")
    return font_path


def unique_path(path: str) -> str:
    """Avoid overwrite: 'file.pdf' -> 'file (2).pdf', 'file (3).pdf', ..."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while True:
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def title_case_ptbr(name: str) -> str:
    """Title-case a name using Brazilian Portuguese conventions: every
    word capitalized except connectives (de/da/do/das/dos/e), and the
    first word is always capitalized even if it's a connective."""
    words = (name or "").strip().split()
    if not words:
        return name or ""
    result = []
    for i, word in enumerate(words):
        lower = word.lower()
        if i > 0 and lower in _PTBR_LOWERCASE_CONNECTIVES:
            result.append(lower)
        else:
            # Capitalize handling hyphenated names like "Maria-Clara"
            result.append("-".join(p[:1].upper() + p[1:].lower() if p else p
                                    for p in word.split("-")))
    return " ".join(result)


def apply_name_case(name: str, mode: str) -> str:
    """mode: 'none' | 'title' | 'upper'."""
    if mode == "title":
        return title_case_ptbr(name)
    if mode == "upper":
        return name.upper()
    return name


def safe_format(template: str, **kwargs) -> str:
    """Literal placeholder substitution -- NOT str.format().

    Fixes baseline Known Issue #6: str.format() raises KeyError/IndexError
    the moment a user types a stray '{' or '}' into a free-text template
    (e.g. an email subject/body), silently failing that send. This does a
    plain substring replace per known placeholder instead, so arbitrary
    braces in the surrounding text are inert.
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result
