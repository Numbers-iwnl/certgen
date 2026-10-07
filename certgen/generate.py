"""
GenerationEngine: orchestrates turning (template + records) into one PDF
per person plus the send-control CSV.

This replaces the baseline's _generate_worker, with two structural fixes
baked in from the start (see PARITY.md #3, #4) rather than patched after
the fact:

  - No Tk/Qt state is touched from here. The engine takes plain Python
    values in, reports progress through plain callbacks, and every
    UI toolkit sees the exact same engine. That's what makes "Tk
    variables read from a worker thread" (Known Issue #3) structurally
    impossible rather than something to remember not to do.

  - Known Issue #4 (recomputing snap candidates from scratch per field
    per record): offsets/snap/tolerance are constant for a field across
    a whole batch, so the EFFECTIVE RECT, the auto-picked TEXT COLOR, and
    (when enabled) the CONSISTENT FONT SIZE are each computed exactly
    once per batch in _precompute(), then reused for every record. Only
    the drawn text differs per record.

Phase 5 additions (all optional, off by default, so default behavior
matches the baseline exactly): a global date override, a filename
template, ZIP export, a unique certificate ID with an optional QR code,
and a soft PDF permission lock against casual edits.
"""
import base64
import datetime
import os
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pymupdf as fitz

from . import fonts as fontmod
from .color import pick_text_color
from .control_csv import write_send_control_csv
from .fields import ALL_FIELDS, FIELD_CPF, FIELD_DATE, FIELD_EMAIL, FIELD_NAME, FIELD_TURMA
from .render import draw_text_centered, draw_text_left
from .snap import SnapContext
from .template_config import TemplateConfig
from .textutil import apply_name_case, format_cpf, safe_format, sanitize_filename, \
    timestamp, truncate_for_path_limits, unique_path

ProgressCb = Callable[[int, int], None]
LogCb = Callable[[str], None]
CancelledCb = Callable[[], bool]


@dataclass
class FieldSettings:
    offset_x: float = 0.0
    offset_y: float = 0.0
    snap_enabled: bool = True
    snap_tol: float = 24.0
    baseline_tweak_ems: float = 0.0
    font_override: float = 0.0  # 0 = automatic
    bold: bool = False
    use_consistent_size: bool = False  # meaningful for FIELD_NAME only


@dataclass
class GenerationOptions:
    template_pdf: str
    font_path: str
    evento: str
    output_dir: str
    merge_pdf: bool = False
    name_case_mode: str = "none"  # "none" | "title" | "upper"
    default_turma: str = ""
    default_date_override: str = ""  # non-empty -> used for every record
    filename_template: str = "Certificado - {evento} - {nome}"
    make_zip: bool = False
    add_cert_id: bool = False
    add_qr: bool = False
    qr_verify_base_url: str = ""
    lock_pdf: bool = False
    sample_limit: Optional[int] = None  # dry-run: only the first N (+ worst case)


@dataclass
class GenerationResult:
    ok: int = 0
    fail: int = 0
    cancelled: bool = False
    outdir: str = ""
    control_csv_path: str = ""
    merged_pdf_path: str = ""
    zip_path: str = ""
    is_sample: bool = False


def _make_cert_id(evento: str, idx: int) -> str:
    slug = sanitize_filename(evento).replace(" ", "")[:14].upper() or "EVT"
    return f"{slug}-{idx:05d}-{uuid.uuid4().hex[:6].upper()}"


def _make_qr_image_bytes(data: str) -> bytes:
    import io
    import qrcode
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _lock_permissions_kwargs() -> dict:
    owner_pw = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii")
    perms = (fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ |
             fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY)
    return dict(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=owner_pw, user_pw="", permissions=perms)


class GenerationEngine:
    def __init__(self, cfg: TemplateConfig, field_settings: Dict[str, FieldSettings],
                 options: GenerationOptions):
        self.cfg = cfg
        self.field_settings = field_settings
        self.options = options

    def _raw_rects(self) -> Dict[str, fitz.Rect]:
        rects: Dict[str, fitz.Rect] = {}
        for f, fc in self.cfg.fields.items():
            if fc.page_index == 0:
                rects[f] = fitz.Rect(*fc.rect)
        return rects

    def _precompute(self, records: List[Dict[str, str]]):
        """Everything that's constant across the whole batch: effective
        (snapped+offset) rects, auto text colors, and -- if enabled -- one
        common font size for every name. Computed once, reused per record."""
        raw_rects = self._raw_rects()
        if FIELD_NAME not in raw_rects:
            doc = fitz.open(self.options.template_pdf)
            try:
                from .detect import compute_auto_area_firstpage
                raw_rects[FIELD_NAME] = compute_auto_area_firstpage(doc)
            finally:
                doc.close()

        doc = fitz.open(self.options.template_pdf)
        try:
            page = doc[0]
            snap_ctx = SnapContext(page)

            effective: Dict[str, fitz.Rect] = {}
            colors: Dict[str, Tuple[float, float, float]] = {}
            for f, raw in raw_rects.items():
                fs = self.field_settings.get(f, FieldSettings())
                eff = snap_ctx.effective_rect(raw, fs.snap_enabled, fs.snap_tol, fs.offset_x, fs.offset_y)
                effective[f] = eff
                colors[f] = pick_text_color(page, eff)

            common_name_size: Optional[float] = None
            name_settings = self.field_settings.get(FIELD_NAME, FieldSettings())
            if name_settings.use_consistent_size and records:
                names = [apply_name_case(r.get(FIELD_NAME, "").strip(), self.options.name_case_mode)
                         for r in records if r.get(FIELD_NAME)]
                if len(names) > 800:
                    step = max(1, len(names) // 800)
                    names = names[::step]
                common_name_size = fontmod.common_font_size_for_all(
                    names, effective[FIELD_NAME], self.options.font_path)

            return effective, colors, common_name_size
        finally:
            doc.close()

    def _select_records(self, records: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], bool]:
        limit = self.options.sample_limit
        if not limit or limit >= len(records):
            return records, False
        sample = list(records[:limit])
        longest = max(records, key=lambda r: len(r.get(FIELD_NAME, "") or ""))
        if longest not in sample:
            sample[-1] = longest
        return sample, True

    def _resolve_output_dir(self, is_sample: bool) -> str:
        outdir = self.options.output_dir.strip()
        if not outdir:
            base = os.path.dirname(self.options.template_pdf) or os.getcwd()
            outdir = os.path.join(base, f"Certificados - {sanitize_filename(self.options.evento)} - {timestamp()}")
        if is_sample:
            outdir = os.path.join(outdir, "_amostra")
        os.makedirs(outdir, exist_ok=True)
        return outdir

    def run(self, records: List[Dict[str, str]],
            progress_cb: Optional[ProgressCb] = None,
            log_cb: Optional[LogCb] = None,
            is_cancelled: Optional[CancelledCb] = None) -> GenerationResult:

        def log(msg: str):
            if log_cb:
                log_cb(msg)

        opt = self.options
        records, is_sample = self._select_records(records)
        effective, colors, common_name_size = self._precompute(records)
        outdir = self._resolve_output_dir(is_sample)

        total = len(records)
        ok = fail = 0
        control_rows: List[Dict[str, str]] = []
        merged_doc = fitz.Document() if (opt.merge_pdf and not is_sample) else None
        cancelled = False

        for idx, rec in enumerate(records, start=1):
            if is_cancelled and is_cancelled():
                log("Cancelado.")
                cancelled = True
                break
            try:
                doc = fitz.open(opt.template_pdf)
                try:
                    page = doc[0]
                    name = apply_name_case(rec.get(FIELD_NAME, "").strip(), opt.name_case_mode)
                    if not name:
                        raise ValueError("Registro sem nome.")

                    date_str = opt.default_date_override.strip() or \
                        (rec.get(FIELD_DATE, "").strip() or datetime.date.today().strftime("%d/%m/%Y"))
                    turma_str = rec.get(FIELD_TURMA, "").strip() or opt.default_turma
                    cpf_str = rec.get(FIELD_CPF, "").strip()
                    if FIELD_CPF in self.cfg.required:
                        if not cpf_str:
                            raise ValueError("CPF requerido, mas ausente na planilha.")
                        cpf_str = format_cpf(cpf_str)

                    name_fs = self.field_settings.get(FIELD_NAME, FieldSettings())
                    if name_fs.font_override > 0:
                        size = name_fs.font_override
                    elif common_name_size is not None:
                        size = common_name_size
                    else:
                        size = fontmod.autosize_font_to_rect(name, effective[FIELD_NAME], opt.font_path)
                    draw_text_centered(page, effective[FIELD_NAME], name, opt.font_path, size,
                                        baseline_tweak_ems=name_fs.baseline_tweak_ems,
                                        color=colors.get(FIELD_NAME, (0, 0, 0)), bold=False)

                    for f, text in [(FIELD_CPF, cpf_str), (FIELD_DATE, date_str), (FIELD_TURMA, turma_str)]:
                        if f in self.cfg.required and f in effective and text:
                            fs = self.field_settings.get(f, FieldSettings())
                            size2 = fs.font_override if fs.font_override > 0 else \
                                fontmod.autosize_font_to_rect(text, effective[f], opt.font_path)
                            draw_text_left(page, effective[f], text, opt.font_path, size2,
                                           baseline_tweak_ems=fs.baseline_tweak_ems,
                                           color=colors.get(f, (0, 0, 0)), bold=fs.bold)

                    cert_id = ""
                    if opt.add_cert_id or opt.add_qr:
                        cert_id = _make_cert_id(opt.evento, idx)
                        self._stamp_cert_id(page, cert_id)

                    filename = safe_format(opt.filename_template, evento=opt.evento, nome=name,
                                            cpf=cpf_str, turma=turma_str, data=date_str) + ".pdf"
                    filename = sanitize_filename(filename)
                    filename = truncate_for_path_limits(outdir, filename)
                    outpath = unique_path(os.path.join(outdir, filename))

                    save_kwargs = _lock_permissions_kwargs() if (opt.lock_pdf and not is_sample) else {}
                    if opt.add_cert_id or opt.add_qr:
                        doc.set_metadata({**doc.metadata, "keywords": f"cert_id:{cert_id}"})
                    doc.save(outpath, **save_kwargs)

                    if not is_sample:
                        control_rows.append({
                            "nome": name, "email": rec.get(FIELD_EMAIL, "").strip(),
                            "cpf": cpf_str, "turma": turma_str, "data": date_str,
                            "pdf_arquivo": os.path.basename(outpath), "pdf_caminho": outpath,
                            "status_envio": "pendente", "erro_envio": "", "enviado_em": "",
                        })
                        if merged_doc is not None:
                            try:
                                merged_doc.insert_pdf(doc)
                            except Exception as ie:
                                log(f"(!) Falha ao montar PDF único: {ie}")

                    ok += 1
                    log(f"[{idx}/{total}] OK: {name}")
                finally:
                    doc.close()
            except Exception as e:
                fail += 1
                log(f"[{idx}/{total}] ERRO: {rec.get(FIELD_NAME,'(sem nome)')} -> {e}")

            if progress_cb:
                progress_cb(idx, total)

        result = GenerationResult(ok=ok, fail=fail, cancelled=cancelled, outdir=outdir, is_sample=is_sample)

        if merged_doc is not None and ok > 0:
            try:
                merged_path = unique_path(os.path.join(outdir, f"Lote — {sanitize_filename(opt.evento)}.pdf"))
                merged_doc.save(merged_path)
                result.merged_pdf_path = merged_path
                log(f"PDF único criado: {merged_path}")
            except Exception as e:
                log(f"Falha ao criar PDF único: {e}")
            finally:
                merged_doc.close()

        if control_rows:
            try:
                result.control_csv_path = write_send_control_csv(outdir, opt.evento, control_rows)
                log(f"Controle de envio salvo: {result.control_csv_path}")
            except Exception as e:
                log(f"Falha ao salvar controle de envio: {e}")

        if opt.make_zip and ok > 0 and not is_sample:
            try:
                result.zip_path = self._make_zip(outdir, opt.evento, control_rows, result.merged_pdf_path)
                log(f"ZIP criado: {result.zip_path}")
            except Exception as e:
                log(f"Falha ao criar ZIP: {e}")

        return result

    def _stamp_cert_id(self, page: fitz.Page, cert_id: str) -> None:
        pw, ph = page.rect.width, page.rect.height
        margin = pw * 0.02
        qr_size = min(pw, ph) * 0.08

        if self.options.add_qr:
            qr_data = (self.options.qr_verify_base_url.strip() + cert_id) \
                if self.options.qr_verify_base_url.strip() else cert_id
            try:
                png_bytes = _make_qr_image_bytes(qr_data)
                qr_rect = fitz.Rect(pw - margin - qr_size, ph - margin - qr_size,
                                     pw - margin, ph - margin)
                page.insert_image(qr_rect, stream=png_bytes)
            except Exception:
                pass

        try:
            label_rect = fitz.Rect(margin, ph - margin - 10, margin + 220, ph - margin)
            page.insert_text((label_rect.x0, label_rect.y1), f"ID: {cert_id}",
                              fontsize=6, color=(0.55, 0.55, 0.55))
        except Exception:
            pass

    def _make_zip(self, outdir: str, evento: str, control_rows: List[Dict[str, str]],
                   merged_pdf_path: str) -> str:
        zip_path = unique_path(os.path.join(outdir, f"Certificados - {sanitize_filename(evento)}.zip"))
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for row in control_rows:
                p = row.get("pdf_caminho", "")
                if p and os.path.isfile(p):
                    zf.write(p, arcname=os.path.basename(p))
            if merged_pdf_path and os.path.isfile(merged_pdf_path):
                zf.write(merged_pdf_path, arcname=os.path.basename(merged_pdf_path))
        return zip_path
