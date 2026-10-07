"""
Pre-flight validation: catches the mistakes that used to only surface
after generating (or worse, emailing) a few hundred certificates --
missing emails, malformed CPFs, duplicate names, and names that will be
squeezed down to an unreadably small font size.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List

from . import fonts as fontmod
from .fields import FIELD_CPF, FIELD_EMAIL, FIELD_NAME
from .generate import FieldSettings, GenerationOptions

_MIN_READABLE_FONT_SIZE = 14.0
_CPF_DIGITS_RE = re.compile(r"\D")


@dataclass
class PreflightReport:
    total_records: int = 0
    missing_email: List[str] = field(default_factory=list)
    invalid_cpf: List[str] = field(default_factory=list)
    duplicate_names: List[str] = field(default_factory=list)
    names_too_small: List[str] = field(default_factory=list)

    @property
    def has_warnings(self) -> bool:
        return bool(self.missing_email or self.invalid_cpf or
                     self.duplicate_names or self.names_too_small)


def run_preflight(records: List[Dict[str, str]], required_fields: List[str],
                   name_rect, font_path: str, name_case_mode: str,
                   needs_email: bool = False) -> PreflightReport:
    from .textutil import apply_name_case

    report = PreflightReport(total_records=len(records))
    seen_names: Dict[str, int] = {}

    for rec in records:
        name = apply_name_case(rec.get(FIELD_NAME, "").strip(), name_case_mode)
        if not name:
            continue

        seen_names[name] = seen_names.get(name, 0) + 1

        if needs_email and not rec.get(FIELD_EMAIL, "").strip():
            report.missing_email.append(name)

        if FIELD_CPF in required_fields:
            digits = _CPF_DIGITS_RE.sub("", rec.get(FIELD_CPF, ""))
            if len(digits) != 11:
                report.invalid_cpf.append(name)

        if name_rect is not None and font_path:
            try:
                size = fontmod.autosize_font_to_rect(name, name_rect, font_path)
                if size <= _MIN_READABLE_FONT_SIZE:
                    report.names_too_small.append(name)
            except Exception:
                pass

    report.duplicate_names = sorted(n for n, count in seen_names.items() if count > 1)
    return report
