# PLAN.md — Gerador de Certificados rewrite

## Status: Phases 0-5 complete (v2.0.0)

The app ships as `main.py` on `certgen/` (headless core) + `ui/` (PySide6).
185 tests pass. The onefile exe builds clean at ~76MB and was verified to
launch, render, persist settings via `%APPDATA%`, single-instance-guard
correctly, and run the full generate → PDF → control-CSV pipeline
end-to-end against a synthetic template. See "What actually shipped"
after each phase below for the honest diff against what was originally
planned — a couple of items were deferred, one gap was caught and fixed
during verification (email settings persistence), and DPI handling
turned out to need no code at all.

## Goal

Turn the existing single-file Tkinter tool into a product that:

- does **everything it does today**, verified against `PARITY.md`, plus
  the improvements below — nothing removed without the user's sign-off;
- ships as **one .exe** a non-technical colleague can double-click, no
  install, no Python, no dependencies to explain;
- is simple enough for non-technical staff to drive without a tutorial
  call. Simplicity is the tiebreaker on every UI decision.

Constraints fixed by the user:
- Onefile PyInstaller build (single shareable exe), not onedir.
- No code-signing certificate available — the exe will trigger Windows
  SmartScreen for first-time runners. Not fixable in code; the user is
  aware.
- Full ground-up rebuild of the calibration/preview UI (Phase 3), not an
  incremental patch of the current layout.

## Decision: Python stays, Tkinter goes, PySide6 (Qt) comes in

- **PyMuPDF stays the rendering engine.** All of the app's actual
  correctness — font metrics, autosize binary search, baseline math, snap
  candidates, per-label style detection, per-rect luminance sampling —
  is built on `fitz`/`pymupdf`. Reimplementing that in another language
  would mean rewriting the one part of this app that's already
  subtle and correct, with no reference to check the port against. Not
  worth the risk against the "don't do less than today" constraint.
- **Tkinter is replaced by PySide6** for everything UI. The ground-up
  Phase 3 canvas (drag/resize boxes over a live PDF preview) is a
  `QGraphicsView`/`QGraphicsItem` job — Tk's Canvas would mean hand-rolling
  hit-testing, resize handles, and cursor management from scratch, which
  is exactly the kind of code where user-facing bugs live. Qt also gives
  thread-safe signals/slots (fixing Known Issue #3 structurally, not by
  discipline), correct high-DPI rendering, and a live-updating results
  table for the email batch screen (Known Issue #12/#13) that
  `ttk.Treeview` can't do gracefully.
- **Cost accepted:** exe grows from ~30-40MB to an estimated 60-75MB with
  aggressive excludes (drop QtWebEngine, QML/Quick, Qt3D, Multimedia,
  Charts, translations). Onefile means that's re-extracted to temp on
  every launch → a few seconds of cold start. Mitigated by:
  - PyInstaller's native splash screen, shown *during* extraction, so a
    double-click gets instant visual feedback instead of a dead cursor.
  - A single-instance guard, so impatient double-clicking focuses the
    existing window instead of spawning duplicates.
  Both are mandatory Phase 1 deliverables, not optional polish — without
  them the onefile cold-start cost is a real usability regression for
  the target audience.
- Considered and rejected: CustomTkinter (only fixes cosmetics, leaves
  the canvas/table problems that motivate Phase 3 unsolved); a WebView2-
  hosted web UI (depends on a runtime that may not be present on a given
  colleague's machine — unacceptable single point of failure for a
  "just works" internal tool).

## Phases

### Phase 0 — Safety net (this commit)
- Git repo initialized; baseline committed verbatim before any change.
- `PARITY.md`: exhaustive behavior inventory, doubling as the rewrite's
  acceptance checklist.
- `requirements.txt` / `requirements-dev.txt`: pinned versions for
  everything the current app actually uses (including the two
  try/except-optional packages, `tkinterdnd2` and `sv_ttk`, which had
  never been pinned before — see Parity §8/#17).
- `tests/`: characterization tests (pytest) against current behavior —
  text/filename/CPF utilities, XLSX parsing, template-config JSON
  round-trip (all 3 legacy versions), field auto-detection, font-metrics/
  autosize math, snap math, text-color picking, text drawing, and the
  full `email_sender.send_batch` state machine (resume/retry/limit/
  override/backup) against a mocked SMTP layer. These pin down behavior,
  not desired behavior — Phase 1+ bug fixes will need matching test
  updates, done consciously, not as collateral damage.
- `build.ps1`: reproducible build script (venv → pinned installs → tests
  → PyInstaller), refuses to build on a failing test suite by default.
- Verified: a from-scratch build via `build.ps1` reproduces a working
  exe from the *existing* spec — proving the baseline is buildable and
  giving a real "before" artifact to diff UX against later.
- `legacy/`: the stray `_original.py` / `_wip.py` / `_u201d_lines.txt`
  working files, archived (not deleted).

### Phase 1 — Correctness + distribution — DONE
Fixed Known Issues #1, #2, #3, #4, #5, #6, #7, #8, #11, #14 (see
`PARITY.md` §7 for how each was fixed and where). Plus:
- Persistence moved to `%APPDATA%\GeradorCertificados\` (prefs, presets,
  logs) — fixes #1 for real, independent of onefile/onedir/dev-mode.
  Verified empirically: a path saved by a dev-mode run was read back
  correctly by the packaged exe.
- Rotating log file + global exception hook with a `CrashDialog` showing
  the traceback and log path — fixes #7.
- Version string in the title bar and embedded in the exe's Windows file
  properties via `version_info.txt` — verified with `Get-Item ...
  .VersionInfo`.
- PyInstaller native splash screen (shown by the bootloader itself,
  before Python even starts) + a `QLocalServer`/`QLocalSocket`
  single-instance guard — verified: a second launch's process exits on
  its own after signaling the first instance to focus.
- Trimmed PyInstaller spec: explicit `PySide6.*` excludes (WebEngine,
  QML/Quick, 3D, Multimedia, Charts, ...) instead of the default hook's
  everything-included behavior, UPX off. Final exe: ~76MB.
- **What actually shipped differently than planned**: DPI awareness
  needed no code — Qt 6's high-DPI scaling is on by default, unlike Qt 5.

### Phase 2 — Extract the core — DONE (merged into Phase 1's delivery)
Landed as `certgen/`: `fields.py`, `fonts.py`, `detect.py`, `snap.py`,
`color.py`, `render.py`, `template_config.py`, `xlsx_source.py`,
`control_csv.py`, `mailer.py`, `generate.py`, `preview.py`,
`preflight.py`, `paths.py`, `prefs.py`, `presets.py`, `credentials.py`,
`logging_setup.py` — no Qt/Tk import anywhere in the package. 185 tests
exercise it directly.
- **What actually shipped differently than planned**: rather than port
  Phase 1's bug fixes into the doomed Tkinter file and then re-extract
  them, Phase 1 and 2 were done as one motion — the fixes were written
  directly into the new headless modules as they were created. Same
  end state, no throwaway work. The originally-planned `render/`/`data/`/
  `mail/` subpackage split was flattened to one `certgen/` package once
  it was written — the extra directory nesting wasn't earning its keep
  at this module count.

### Phase 3 — UX rebuild, ground up — DONE
Replaced the modal-calibrate-then-blind-nudge flow with direct
manipulation: `ui/canvas_editor.py`'s `CanvasEditor` (`QGraphicsView`)
shows the real rendered certificate as its background image, with a
draggable/resizable box per active field (`_FieldBox`). Dragging a box
edits `TemplateConfig` directly and triggers a debounced re-render using
the *same* `certgen.render` draw calls used for real generation — what
you see is what generates. Numeric precision controls (offset/snap/
baseline/font-size/bold/consistent-size) live in an "Ajustes avançados"
panel next to the canvas, still there for anyone who wants exact values.
- Real log panel (`ui/log_panel.py`) with export — fixes #12.
- "Gerar amostra (3)" dry run (`GenerationOptions.sample_limit`),
  automatically padded to include the longest name so the worst case is
  always checked even in a 3-record sample.
- Column-mapping dialog (`ui/dialogs.ColumnMappingDialog` +
  `certgen.xlsx_source.detect_default_mapping`), opt-in via "Mapear
  colunas..." — the classic positional A-E layout still works with zero
  extra clicks for anyone whose spreadsheet already matches it.
- Pre-flight validation (`certgen.preflight.run_preflight` +
  `PreflightDialog`) before generating: missing emails, invalid CPFs,
  duplicate names, names that will render below a readable font size.
- Named presets (`certgen.presets`) bundling template/font/evento/every
  field setting, picked from a dropdown.
- Debounced (150ms), background-thread-free but non-blocking canvas
  refresh instead of synchronous main-thread redraws on every keystroke.

### Phase 4 — Email overhaul — DONE
- `certgen.mailer.SmtpConnection`: one connection reused for the whole
  batch, with a bounded reconnect-and-retry on transient disconnects —
  fixes #5. Verified: `tests/test_mailer.py::TestSmtpConnection` proves
  exactly one connection is opened across 5 sends.
- `certgen.textutil.safe_format()`: literal placeholder substitution
  instead of `str.format()` — fixes #6.
- Cancel button in `ui/email_window.py`, `EmailWorker.cancel()` +
  `send_batch(is_cancelled=...)` checked between sends — fixes #13.
- Results table (name/status/detail) alongside the log tab.
- `test_mode=True` on `send_batch()`: sends a real test email but never
  writes to the control CSV — fixes #2, the one deliberate behavior
  change flagged loudly (both in `PARITY.md` and in the UI's button
  label: "Enviar 1 teste (não marca ninguém como enviado)").
- Provider presets for Gmail / Microsoft 365 / Hostinger / Zoho with
  correct host/port/SSL and an app-password guidance note per provider.
- DPAPI-encrypted optional password storage (`certgen.credentials`, via
  `ctypes` against `crypt32.dll` — no extra pip dependency).
- Atomic control-CSV writes (temp file + `os.replace()`) — fixes #11.
- **Gap caught during manual verification, then fixed**: the "remember
  password" checkbox was built but its persistence was never wired up —
  caught by opening the actual window and checking, not by the unit
  suite (which was testing `certgen.credentials` in isolation and had no
  reason to notice the UI never called it). Fixed by adding
  `EmailWindow._load_settings()`/`_save_settings()` against
  `certgen.prefs`, plus `tests/test_email_window_persistence.py` — a
  regression test that exercises the *real* `EmailWindow` widget instead
  of mocking around it, specifically so a wiring gap like this fails the
  suite next time instead of requiring another manual click-through.

### Phase 5 — Product features — DONE (two items deferred, see below)
Shipped, all opt-in and off by default in `GenerationOptions` so nothing
changes unless a user turns it on:
- ZIP export of a completed batch (`GenerationEngine._make_zip`).
- Unique certificate ID (`EVENTO-00001-A1B2C3` style) stamped as tiny
  footer text and embedded in PDF metadata.
- Optional QR code (via the `qrcode` package) encoding the ID, or a
  verification URL + ID if one is configured.
- Soft PDF permission lock (`fitz.PDF_ENCRYPT_AES_256`, empty user
  password, random discarded owner password, print/copy/accessibility
  allowed but modify/annotate/form/assemble denied) — deliberately
  described as *soft*: PDF permission flags are advisory and a
  determined user with the right tools can still strip them. It stops
  casual in-Acrobat editing, not a determined attacker.
- Correct PT-BR title casing (`textutil.title_case_ptbr`) — fixes #10.
- Global batch date override (`GenerationOptions.default_date_override`).
- Filename templates (`GenerationOptions.filename_template`, default
  unchanged: `"Certificado - {evento} - {nome}"`).
- **Deferred, not shipped**: multi-page template support (the data model
  already carries `page_index` per field, but the canvas only edits page
  0 — extending it to a page selector is straightforward future work,
  not done here) and update-check against a network share (too
  infrastructure-specific to guess at without knowing what network
  storage, if any, this company actually has).

## Working rules for this rewrite

1. Every phase leaves the app in a runnable, demo-able state — no
   "trust me, phase 4 fixes phase 3's half-finished thing."
2. A behavior change (not a bug fix, an intentional UX change) gets
   flagged to the user before or at the point it lands, not buried in a
   commit message.
3. `tests/` grows with the code — new modules extracted in Phase 2 get
   their tests moved/adapted alongside them, never left behind.
4. `PARITY.md` is updated the moment a Known Issue is fixed, so it stays
   an accurate map of "what's left" rather than going stale.
