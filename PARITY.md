# PARITY.md — behavior inventory of the baseline app

**Status: Phases 0-5 complete (v2.0.0).** The app is now PySide6 (`main.py`
+ `certgen/` + `ui/`) instead of Tkinter (`legacy/CriadorDeCertificados.py`,
kept for reference, no longer run). Every Known Issue in §7 is fixed;
each entry below says how. The rest of this document (§1-6, §8) still
describes behavior that must hold — it's the parity contract the rewrite
was built against, not just baseline history.

Purpose: this is the acceptance checklist for the Phase 1-5 rewrite. Every
item below is something the app at commit `2c94f1b` (tag `baseline`) does.
Nothing on this list may silently disappear during the rewrite. If a phase
intentionally changes one of these, it must be called out explicitly in
that phase's notes, not discovered later as a surprise.

Source of truth: `CriadorDeCertificados.py` (2560 lines) and
`email_sender.py`, as committed in the baseline. Line numbers below refer
to that commit and will drift — treat them as pointers, not guarantees,
once the code is restructured.

Characterization tests in `tests/` encode the parts of this list that are
mechanically checkable (pure functions, file formats, CSV/JSON round
trips). UI interaction and visual layout are not covered by automated
tests and must be checked by hand against this document.

---

## 1. Inputs

- **Template PDF** (required). Any PDF; only page 1 is used for field
  detection/placement. Chosen via file dialog or drag-and-drop onto the
  entry field (drag-and-drop requires `tkinterdnd2`; app runs fine without
  it, silently disabling that one convenience).
- **Spreadsheet (.xlsx)** (required). Reads the **active worksheet** only,
  positional columns, no header names recognized:
  - A = Nome (required; blank-name rows are silently skipped)
  - B = CPF (optional)
  - C = Turma (optional)
  - D = Data (optional; a `datetime.date` cell is formatted `dd/mm/YYYY`;
    a string cell is passed through verbatim; blank/missing → empty string,
    later defaulted to *today* at generation time)
  - E = Email (optional; required in practice only if emailing)
  - "1ª linha é cabeçalho" checkbox: when on, row 1 is skipped entirely
    (`skip_header=True` → `next(rows)`).
- **Font (.ttf/.otf)** (required). Any TrueType/OpenType file; validated by
  extension only, not by actually parsing it as a font up front.
- **Nome do evento**: free-text combobox with 5 canned suggestions; used
  in output filenames and the control-CSV filename.
- **Pasta onde salvar** (optional): if blank, output dir defaults to
  `<dir of template PDF>/Certificados - <evento> - <timestamp>/`.

## 2. Field detection & calibration

- On loading a template, `TemplateFieldsDialog` asks which of
  Nome/CPF/Data/Turma this template uses (Nome is always on, can't be
  unchecked). Has a "Detectar automaticamente" button that shows ✓/✗ per
  field without closing the dialog.
- **Closing that dialog via the window's X button** (not OK) leaves
  `dlg.required` unset, and the caller falls back to `[FIELD_NAME]` only —
  i.e. it silently behaves as if the user unchecked everything except
  Nome, with no warning that this happened. (See Known Issues #9.)
- After the dialog, the app auto-detects rects for every required field
  and, for the ones auto-detection couldn't find, offers per-field manual
  calibration via `CalibrateWindow` (asks "select manually now?" per
  missing field; declining leaves that field without a rect).
- **Auto-detection heuristics** (`detect_field_rects_firstpage`):
  - Name: searches page 1 for placeholder text variants —
    `"(Seu Nome Aqui)"`, `"Seu Nome Aqui"`, `"( Seu Nome Aqui )"`,
    `"(NOME)"`, `"NOME"`, `"Nome"`, `"(Nome)"` — takes the largest match by
    area, pads it (40% of width, 90% of height), clips to page. If no
    placeholder text is found: falls back to a fixed rect at 60% page
    width, 10% page height, horizontally centered, vertical center at 55%
    of page height.
  - CPF / Turma / Data: searches for the literal labels `CPF`/`Cpf`/`cpf`,
    `TURMA`/`Turma`/`turma`, `DATA`/`Data`/`data` and places a rect to the
    right of the match (`compute_rect_right_of`: width = max(page_width ×
    ratio, anchor.width × 2), height = max(anchor.height × 1.2-1.3,
    page_width × 0.02), vertically centered on the anchor, clipped to
    page). Width ratios: CPF 0.35, Turma 0.18, Data 0.22.
  - Date fallback when no "DATA" label exists: looks for two `/`-bearing
    word tokens on (nearly) the same line (within 2% of page height) and
    builds a rect spanning them, height = 2× the token height (or 3% of
    page height if that's zero).
- **Style auto-detection**: only for Turma — if the font name of the span
  containing "TURMA" (case-insensitive substring match) contains any of
  `bold, black, heavy, semibold, demi, extrabold, ultrabold, medium`, the
  field is flagged bold by default.
- Per-field manual **negrito (bold)** toggle is available only for CPF and
  Turma (radio-disabled for Nome/Data in the UI). "Bold" is *simulated*:
  the same text is drawn 5× at small offsets (`(0,0), (±0.35,0),
  (0,±0.35)`), not a real bold font weight.
- Calibration is persisted next to the template PDF as
  `<template>.pdf.calibration.json` (`CALIBRATION_SUFFIX`), versioned:
  - v1: `{page_index, rect}` (single field, always treated as Nome).
  - v2: `{version, required, fields: {field: {page_index, rect}}}`.
  - v3 (current writer format): adds per-field `style: {bold: bool}`.
  - Loader accepts all three formats.
- Per-field runtime adjustments (not persisted to the calibration JSON,
  reset on app restart — only exist as in-memory `tk.Variable`s):
  - X/Y offset in points (spinboxes, -300..300, step 0.5).
  - Snap on/off (checkbox, default **on**).
  - Snap tolerance in points (spinbox, 0..120, default 24).
  - Baseline tweak in ems (spinbox, -0.3..0.3, step 0.01).
  - Font size override in pt (spinbox, 0..240, step 0.5; **0 means
    automatic**).
  - "Usar o MESMO tamanho para TODOS os nomes" (Nome only): computes one
    font size that fits every name in the spreadsheet (sampled/truncated
    at 800 names for performance during generation, 400 during preview),
    via binary search shared with per-name autosize.
- **Snap algorithm** (`compute_snapped_rect`): when enabled, candidate
  X/Y positions are collected from: text block centers whose vertical
  center is within 2× tolerance of the field's own vertical center (and
  vice versa for Y), the page's own centerline, straight vector-drawing
  lines, rectangle edges/centers from `page.get_drawings()`, and a fixed
  percentage grid (5/10/25/33/50/66/75/90/95% of width; 10/20/33/50/66/
  80/90% of height). The nearest candidate is used only if within
  tolerance; otherwise the original center is kept. Manual X/Y offset is
  applied *after* snapping.
- **Autosize** (`autosize_font_to_rect` / `common_font_size_for_all`):
  binary search between 8pt and 200pt (0.5pt resolution) for the largest
  size where text width ≤ 98% of rect width (1% padding each side) and
  line height ≤ 88% of rect height (6% padding each side, using font
  ascender/descender in ems).
- **Text color**: auto-picked per field by sampling the rect's average
  luminance in the template PDF (downscaled to ≤200px) — white text if
  luminance < 0.40, else black. Not user-overridable.
- **Name capitalization** (batch-wide, applies to Nome only):
  "none" (as in spreadsheet) / "title" (Python `.title()` — note this
  mis-capitalizes Portuguese connectives, e.g. "João Da Silva" — see
  Known Issues #10) / "upper".

## 3. Live preview

- Right pane renders the *entire first page* of the template at current
  window size (capped at 2400px on the long side), with the preview name
  ("Seu Nome" default, or set via "← Maior nome" / "1º nome da planilha"
  buttons) and placeholder values for other active fields (CPF
  `111.222.333-44`, Data = today, Turma `3`) burned in using the exact
  same draw functions as real generation.
- Debounced via `after(120, ...)` on canvas resize; otherwise
  synchronous/blocking on the UI thread on every relevant control change
  (offsets, snap, baseline, font override, bold toggle, consistent-size
  toggle, name-case radio, preview-name keystrokes).
- Falls back to explanatory placeholder text (not a blank canvas) when:
  no template loaded, no Nome rect resolvable, or the file fails to open.

## 4. Generation (`generate()` / `_generate_worker()`)

- Preconditions checked before starting, each with its own
  `messagebox.showwarning`/`showerror`: template file exists; font file
  exists and has a valid extension; evento is non-blank; XLSX exists,
  parses, and has ≥1 record; if CPF is required, at least one row has a
  non-blank CPF (else hard error, generation refused entirely); if Turma
  is required and every row's Turma is blank, prompts once for a default
  Turma value applied to all rows (Cancel aborts generation).
- Runs on a background `threading.Thread`; UI updates flow back through a
  `queue.Queue` pumped every 50ms.
- Per record: opens a **fresh copy** of the template PDF (not reused
  across records), draws Nome centered (color/size/baseline per the rules
  above; font-size priority is manual override > consistent-size >
  per-name autosize), draws CPF/Data/Turma left-aligned for any of those
  in the template's `required` set that have non-empty text, formats CPF
  via `format_cpf` (only if 11 digits, else left as-is), defaults empty
  Data to *today*, defaults empty Turma to the earlier-collected default.
  A record with a blank name raises and is counted as a failure; a
  required-but-missing CPF also raises per-record (in addition to the
  earlier batch-level precheck).
- Output filename: `Certificado - {evento} - {nome}.pdf`, sanitized
  (forbidden Windows chars → `_`), de-duplicated via `unique_path` (never
  overwrites: appends ` (2)`, ` (3)`, ...).
- Progress reporting: percentage, "`{idx} / {total} ({pct}%)`" detail
  label, running failure count appended once any failure occurs, one log
  line per record (`[i/total] OK: name` or `... ERRO: name → error`) —
  but the **log surface is a single status label**, so only the most
  recent line is visible; earlier lines are gone the instant the next one
  arrives (see Known Issues #12).
- Optional "Juntar tudo em 1 PDF": appends every successfully generated
  doc's pages into one merged PDF, saved as `Lote — {evento}.pdf` in the
  same output dir (only if ≥1 success).
- Always writes a **send-control CSV** (`controle_envio - {evento}.csv`,
  `;`-delimited, `utf-8-sig`, one row per successfully generated
  certificate) with columns: nome, email, cpf, turma, data, pdf_arquivo,
  pdf_caminho, status_envio (`pendente`), erro_envio (empty),
  enviado_em (empty). This file is the sole handoff into the email step.
- Cancel button sets a flag checked between records (not mid-record); a
  cancelled run still writes whatever was completed so far, including a
  partial control CSV, and reports "Interrompido: N ok, M falhas."
- On completion (not cancelled): success dialog with counts + paths,
  auto-opens the output folder (`os.startfile` on Windows), refreshes the
  preview.
- A crash anywhere in the worker is caught at the top level, logged, and
  re-enables the Generate button rather than leaving the UI stuck
  disabled.

## 5. Email step (`email_sender.py` + the email window)

- Entirely separate, manually-opened window ("✉ Abrir envio por
  e-mail"). Reopening while already open just refocuses it instead of
  creating a duplicate.
- Inputs: control CSV path (must already exist — generated by a prior
  Step-4 run, or hand-picked via file dialog), SMTP username/password
  (password field has a show/hide toggle), SMTP host (default
  `smtp.hostinger.com`), port (default 465), SSL checkbox (default on;
  when off, uses STARTTLS instead), sender display name (default
  "Equipe do Congresso"), subject (default "Seu certificado do
  congresso"), body template (multi-line, `{nome}` placeholder, default
  Portuguese boilerplate — see `DEFAULT_EMAIL_BODY`), "Receber teste em"
  override address, batch limit (default 2000), delay between sends in
  seconds (default 3).
- **"ENVIAR 1 TESTE"**: requires CSV + username + password + a
  non-blank override address (refuses otherwise). Calls the *same*
  `send_batch` used for real sends, with `limit=1`, `create_backup=False`,
  and `to_override` forced to the test address. **This marks row 1 of the
  control CSV as `enviado` even though the real recipient never got the
  email** — see Known Issues #2. No dedicated "test mode" exists.
- **"ENVIAR LOTE"**: requires CSV + username + password; validates limit
  (>0) and delay (≥0) are integers; shows a confirmation dialog whose text
  differs depending on whether an override address is set ("all N will go
  to X, continue?" vs "this is real, continue?"); on confirm, runs
  `send_batch` in a background thread with a live-updating window title
  showing `sent/limit`.
- **`send_batch` semantics** (`email_sender.py`):
  - Optionally backs up the CSV first (`<path>.<YYYYMMDD_HHMMSS>.bak`,
    plain copy) — on for batch sends, off for the 1-email test.
  - A row is eligible to (re-)send iff its `status_envio`, normalized
    (trimmed + lowercased), is `""`, `"pendente"`, or `"falha"` — i.e.
    **failed sends are automatically retried on the next run**, and
    already-`enviado` rows are permanently skipped (this is the resume
    mechanism the whole feature depends on).
  - Iterates rows in file order; stops accepting new sends once `limit`
    successful sends have happened in *this* run (rows beyond that stay
    untouched at whatever status they had).
  - Recipient = `to_override` if set, else the row's own `email` column;
    a blank effective recipient marks the row `falha` with `"Sem email."`
    without attempting to send.
  - On success: `status_envio="enviado"`, `erro_envio=""`,
    `enviado_em=<now, dd/mm/YYYY HH:MM:SS>`.
  - On any exception building/sending the message (including a missing
    PDF file on disk): `status_envio="falha"`, `erro_envio=str(e)[:300]`,
    `enviado_em=""`.
  - **The CSV is rewritten in full after every single row**, success or
    failure, so a crash mid-batch loses at most the in-flight row's
    status, not the whole run's progress. It is not atomic (no temp file
    + rename), so a crash exactly during that write can corrupt the file
    (see Known Issues #11).
  - Sleeps `delay_seconds` between sends (not after the last one).
  - One SMTP connection is opened, logged in, and closed **per email**
    (see Known Issues #5).
  - Returns a summary dict: backup_path, total, pending_before,
    already_sent_before, sent_now, failed_now, skipped_now, csv_path.
  - `build_message`: subject/from/to headers, `body_template.format(
    nome=nome)` as plaintext body (nome falls back to "Participante" if
    blank) — **any literal `{` or `}` the user types into the body
    template raises `KeyError`/`IndexError` and fails that row** (Known
    Issues #6). Attaches the PDF at `pdf_caminho` under its original
    basename; raises `ValueError` if `pdf_caminho` is blank, or
    `FileNotFoundError` if the file no longer exists on disk.
- No cancel button for an in-progress batch send (Known Issues #13); no
  per-row results table, only the rolling log (Known Issues #12); no
  visibility into a batch on its ~2000×3s ≈ 100-minute upper bound other
  than the window title counter.

## 6. Persistence & app chrome

- `.app_prefs.json` next to the script/exe (via `BASE_DIR =
  dirname(__file__)`) stores `tutorial_shown` and the last-used
  template/xlsx/font paths, restored on next launch (paths that no longer
  exist on disk are silently ignored). **In the packaged onefile exe,
  `__file__` resolves inside the PyInstaller temp extraction dir, which is
  deleted on exit — so none of this actually persists in the distributed
  exe** (Known Issues #1). Confirmed: baseline `dist/GeradorCertificados.exe`
  writes/reads `.app_prefs.json` from a `_MEI*` temp folder that's gone
  on the next launch.
- First-run tutorial dialog (`_show_tutorial`), shown once ever (gated by
  the same broken prefs mechanism — currently effectively shows on every
  onefile-exe launch since the flag never sticks).
- Keyboard shortcuts: Ctrl+O (pick template), Ctrl+Shift+O (pick XLSX),
  Ctrl+F (pick font), Ctrl+G (generate), F1 (shortcuts help dialog).
- "Compact mode" auto-engages when screen ≤1366×768: shrinks sidebar
  width, preview minimums, band height, Tk global scaling (0.9), and
  banner max height.
- Window opens maximized (`state("zoomed")`) with a fallback to explicit
  full-screen geometry if that's unsupported.
- Optional theming: `sv_ttk` light theme if importable (silently skipped
  otherwise); optional drag-and-drop onto the PDF/XLSX/font entries if
  `tkinterdnd2` is importable.
- On window close: best-effort save of last-used paths, then destroy.

## 7. Known issues in the baseline — all fixed as of v2.0.0

These were real defects in the baseline app. Each was fixed as a
*documented, intentional* behavior change (not a side effect of
restructuring), and none was "fixed" by removing the feature it was
attached to.

1. **Prefs don't persist in the packaged exe** — `BASE_DIR` is derived
   from `__file__`, which lives in the PyInstaller onefile temp dir.
   Confirmed against a from-scratch build (see `build.ps1` output):
   `.app_prefs.json` is written to `%TEMP%\_MEI*\`, gone after exit.
   **FIXED**: `certgen/paths.py` resolves persistent state to
   `%APPDATA%\GeradorCertificados\`, never from `__file__`/`_MEIPASS`.
   Verified empirically in v2.0.0: a path saved by a dev-mode run was
   correctly read back by the packaged exe on next launch.
2. **"ENVIAR 1 TESTE" marks a real row as `enviado`** even though the
   email went to the override address, not the real recipient — that
   person silently never receives their certificate unless someone
   notices and manually resets the CSV row.
   **FIXED**: `certgen/mailer.send_batch(test_mode=True)` sends the real
   test email but never writes to `status_envio`/`erro_envio`/
   `enviado_em`. Covered by `tests/test_mailer.py::TestTestMode`.
3. **Tk variables (`tk.DoubleVar`/`BooleanVar`/etc.) are read from the
   background generation thread** (`_generate_worker`), which is not
   safe with Tkinter's threading model — a latent freeze/crash risk, not
   yet observed to crash in practice but structurally unsound.
   **FIXED**: `certgen/generate.GenerationEngine` takes plain values and
   reports through plain callbacks; `ui/workers.py` wraps it in a QThread
   whose signals are the only thing crossing the thread boundary, marshaled
   safely by Qt. No UI-framework state is ever touched from a worker.
4. **Snap candidates are recomputed from scratch per field per record**
   (`get_text("blocks")` + `get_text("words")` + `get_drawings()` on a
   freshly-opened doc, every single record) even though the result is
   identical across the whole batch. Measurable slowdown at scale (2000+
   records × up to 4 fields).
   **FIXED**: `certgen/snap.SnapContext` collects candidates once per
   page; `GenerationEngine._precompute()` computes the effective rect,
   color, and (if enabled) shared name font size exactly once per batch.
5. **A new SMTP connection is opened per email** rather than reused for
   the batch — slow, and more likely to trip provider rate limiting.
   **FIXED**: `certgen/mailer.SmtpConnection` holds one connection for
   the whole batch, with a bounded reconnect-and-retry on disconnects.
   Covered by `tests/test_mailer.py::TestSmtpConnection`.
6. **Unescaped `str.format(nome=...)` on user-authored email body text**
   — a stray `{` or `}` typed into the body template breaks that send.
   **FIXED**: `certgen/textutil.safe_format()` does literal placeholder
   substring replacement instead of `str.format()`.
7. **stderr is discarded** — the spec builds with `console=False`, so
   every `log_warn`/`log_err`/traceback vanishes into nothing in the
   distributed exe. No log file exists anywhere.
   **FIXED**: `certgen/logging_setup.py` writes a rotating log file under
   `%APPDATA%\GeradorCertificados\logs\`; a global excepthook shows a
   `CrashDialog` with the traceback and the log file path.
8. **No handling for Windows path-length limits or reserved filenames**
   (`CON`, `PRN`, `NUL`, ...) in generated certificate filenames.
   **FIXED**: `textutil.sanitize_filename()` prefixes reserved device
   names; `textutil.truncate_for_path_limits()` trims long filenames
   (keeping the extension) before `GenerationEngine` writes them.
9. **Closing `TemplateFieldsDialog` via the window's X** silently
   degrades to "only Nome is required" with no warning, indistinguishable
   from a deliberate choice.
   **FIXED**: `ui/main_window.py::_after_pick_template` now shows an
   explicit dialog naming which fields will be used and how to reopen
   the choice, instead of silently falling back.
10. **`.title()` for name capitalization is wrong for Portuguese**
    (`"joão da silva".title()` → `"João Da Silva"`, capitalizing
    connective words that shouldn't be).
    **FIXED**: `certgen/textutil.title_case_ptbr()` keeps de/da/do/das/
    dos/e/di/du lowercase except as the first word.
11. **Control CSV is rewritten non-atomically** on every row during
    sending — no temp-file-plus-rename, so a crash during that specific
    write can corrupt the file the resume mechanism depends on.
    **FIXED**: `certgen/control_csv.py` writes to a temp file and
    `os.replace()`s it into place.
12. **No real log panel** — one status label shows only the latest line;
    with any meaningful failure count, earlier failures are unreadable
    without re-running.
    **FIXED**: `ui/log_panel.py` is a real scrolling, exportable log; the
    email window additionally has a per-row results table.
13. **No cancel control for an in-progress email batch** (generation has
    one; sending doesn't).
    **FIXED**: `EmailWorker.cancel()` + `send_batch(is_cancelled=...)`
    checked between sends; the email window has a Cancelar button.
14. **No version identifier anywhere** in the UI or the exe's file
    properties — impossible to ask "which build do you have?" once this
    is passed around the company.
    **FIXED**: version shown in the window title bar (`certgen/version.py`)
    and embedded in the exe's Windows file properties via
    `version_info.txt`, verified via `Get-Item ... .VersionInfo`.
15. **`import fitz` triggers a PyMuPDF deprecation warning** at import
    time (`pymupdf` is the non-deprecated alias) — harmless today, but
    noise that will eventually break when the alias is removed upstream.
    **FIXED**: every module uses `import pymupdf as fitz`.
16. **`_update_wraplengths` throws "unknown option -wraplength"** when
    `sv_ttk`'s theme is active, swallowed by a bare `except Exception`.
    **MOOT**: Tkinter and `sv_ttk` are gone entirely; the Qt UI has no
    equivalent code path.
17. **Whether the previously-distributed `dist/GeradorCertificados.exe`
    (52MB) actually included `tkinterdnd2`/`sv_ttk` is unknown** — neither
    was pinned anywhere before this repo existed.
    **MOOT**: both packages are gone from `requirements.txt` — PySide6
    has native drag-and-drop and its own theming, so neither was ever
    needed in the rewrite.

## 8. Build

- `GeradorCertificados.spec`: PyInstaller onefile-equivalent (single
  `EXE` combining scripts+binaries+datas), `console=False`,
  `icon=assets\logo.ico`, `upx=True`, bundles `assets/` verbatim plus
  `collect_all()` for `fitz`, `PIL`, `openpyxl` (broad — pulls in far more
  than is used, e.g. every PIL image-format plugin).
- No pinned dependency versions existed before this repo (`requirements.txt`
  in this commit is the first). No build script existed before `build.ps1`
  in this commit.
