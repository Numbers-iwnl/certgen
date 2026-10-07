import os
from typing import Dict, List, Optional

import pymupdf as fitz
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                                QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                                QMainWindow, QProgressBar, QPushButton, QRadioButton,
                                QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget,
                                QVBoxLayout, QWidget)

from certgen import prefs, presets
from certgen.detect import compute_auto_area_firstpage, detect_field_rects_firstpage, \
    detect_field_styles_firstpage
from certgen.fields import ALL_FIELDS, FIELD_CPF, FIELD_DATE, FIELD_NAME, FIELD_TITLES, FIELD_TURMA
from certgen.generate import FieldSettings, GenerationEngine, GenerationOptions
from certgen.paths import asset
from certgen.preflight import run_preflight
from certgen.preview import render_preview_doc
from certgen.template_config import FieldCalibration, TemplateConfig, load_template_config, \
    save_template_config
from certgen.textutil import apply_name_case, ensure_font_file
from certgen.version import APP_NAME, __version__
from certgen.xlsx_source import detect_default_mapping, read_records_from_xlsx, \
    read_records_with_mapping, sniff_headers

from ui import msgbox
from ui.canvas_editor import CanvasEditor, render_page_to_qimage
from ui.dialogs import ColumnMappingDialog, PreflightDialog, TemplateFieldsDialog
from ui.email_window import EmailWindow
from ui.log_panel import LogPanel
from ui.workers import GenerationWorker

PREVIEW_TEXTS_SAMPLE = {
    FIELD_CPF: "111.222.333-44",
    FIELD_DATE: "01/01/2026",
    FIELD_TURMA: "Turma 3",
}


class _DropLineEdit(QLineEdit):
    """A QLineEdit that also accepts a dropped file, calling on_drop(path)."""

    def __init__(self, extensions, on_drop, parent=None):
        super().__init__(parent)
        self._extensions = extensions
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path.lower().endswith(tuple(self._extensions)):
            self.setText(path)
            self._on_drop(path)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{__version__}")
        self.resize(1400, 900)

        self.template_pdf = ""
        self.xlsx_path = ""
        self.font_path = ""
        self.evento = "Workshop de Inovação"
        self.output_dir = ""
        self.xlsx_has_header = False
        self.column_mapping: Optional[Dict[str, Optional[int]]] = None
        self.name_case_mode = "none"
        self.merge_pdf = False
        self.preview_name = "Seu Nome"

        self.template_cfg: TemplateConfig = TemplateConfig(required=[FIELD_NAME], fields={})
        self.field_settings: Dict[str, FieldSettings] = {f: FieldSettings() for f in ALL_FIELDS}
        self.adjust_field = FIELD_NAME

        self._worker: Optional[GenerationWorker] = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._do_refresh_canvas)

        self._email_window: Optional[EmailWindow] = None

        self._build_ui()
        self._bind_shortcuts()
        QTimer.singleShot(300, self._load_saved_paths)

    # ---------- UI construction ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setObjectName("headerBand")
        header.setFixedHeight(48)
        hl = QHBoxLayout(header)
        title = QLabel(APP_NAME)
        title.setObjectName("headerTitle")
        version = QLabel(f"v{__version__}")
        version.setObjectName("headerVersion")
        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(version)
        root.addWidget(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([420, 660, 340])

    def _build_left_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)

        # --- Files ---
        files_box = QGroupBox("Arquivos")
        f = QFormLayout(files_box)

        pdf_row = QHBoxLayout()
        self.pdf_edit = _DropLineEdit([".pdf"], self._after_pick_template)
        pdf_btn = QPushButton("Escolher...")
        pdf_btn.clicked.connect(self.pick_template)
        pdf_row.addWidget(self.pdf_edit)
        pdf_row.addWidget(pdf_btn)
        f.addRow("Modelo (PDF):", pdf_row)

        xlsx_row = QHBoxLayout()
        self.xlsx_edit = _DropLineEdit([".xlsx"], self._after_pick_xlsx)
        xlsx_btn = QPushButton("Escolher...")
        xlsx_btn.clicked.connect(self.pick_xlsx)
        xlsx_row.addWidget(self.xlsx_edit)
        xlsx_row.addWidget(xlsx_btn)
        f.addRow("Planilha (.xlsx):", xlsx_row)

        self.header_check = QCheckBox("1ª linha é cabeçalho")
        self.header_check.toggled.connect(self._on_header_toggle)
        f.addRow("", self.header_check)

        xlsx_sub = QHBoxLayout()
        self.map_columns_btn = QPushButton("Mapear colunas...")
        self.map_columns_btn.clicked.connect(self._open_column_mapping)
        self.xlsx_count_label = QLabel("")
        self.xlsx_count_label.setProperty("role", "hint")
        self.xlsx_count_label.setWordWrap(True)
        xlsx_sub.addWidget(self.map_columns_btn)
        xlsx_sub.addWidget(self.xlsx_count_label, 1)
        f.addRow("", xlsx_sub)

        font_row = QHBoxLayout()
        self.font_edit = _DropLineEdit([".ttf", ".otf"], self._after_pick_font)
        font_btn = QPushButton("Escolher...")
        font_btn.clicked.connect(self.pick_font)
        font_row.addWidget(self.font_edit)
        font_row.addWidget(font_btn)
        f.addRow("Fonte (.ttf/.otf):", font_row)

        self.evento_combo = QComboBox()
        self.evento_combo.setEditable(True)
        self.evento_combo.addItems(["Workshop de Inovação", "Curso de Extensão",
                                     "Semana Acadêmica", "Congresso Anual", "Jornada Científica"])
        self.evento_combo.setCurrentText(self.evento)
        self.evento_combo.currentTextChanged.connect(self._on_evento_changed)
        f.addRow("Nome do evento:", self.evento_combo)

        outdir_row = QHBoxLayout()
        self.outdir_edit = QLineEdit()
        outdir_btn = QPushButton("Escolher...")
        outdir_btn.clicked.connect(self.pick_output_dir)
        outdir_row.addWidget(self.outdir_edit)
        outdir_row.addWidget(outdir_btn)
        f.addRow("Pasta de saída (opcional):", outdir_row)

        layout.addWidget(files_box)

        # --- Active field ---
        field_box = QGroupBox("Campo em edição no canvas")
        field_layout = QGridLayout(field_box)
        self.field_radios: Dict[str, QRadioButton] = {}
        for i, field in enumerate(ALL_FIELDS):
            rb = QRadioButton(FIELD_TITLES[field])
            rb.toggled.connect(lambda checked, f=field: self._on_active_field_radio(f, checked))
            self.field_radios[field] = rb
            field_layout.addWidget(rb, i // 2, i % 2)
        self.field_radios[FIELD_NAME].setChecked(True)
        layout.addWidget(field_box)

        # --- Advanced adjustments ---
        adv_box = QGroupBox("Ajustes avançados do campo selecionado")
        adv = QFormLayout(adv_box)

        self.snap_check = QCheckBox("Alinhar automaticamente (snap)")
        self.snap_check.setChecked(True)
        self.snap_check.toggled.connect(self._on_field_setting_changed)
        adv.addRow(self.snap_check)

        self.snap_tol_spin = QDoubleSpinBox()
        self.snap_tol_spin.setRange(0, 120)
        self.snap_tol_spin.setValue(24)
        self.snap_tol_spin.valueChanged.connect(self._on_field_setting_changed)
        adv.addRow("Distância do snap (pt):", self.snap_tol_spin)

        self.offset_x_spin = QDoubleSpinBox()
        self.offset_x_spin.setRange(-300, 300)
        self.offset_x_spin.setSingleStep(0.5)
        self.offset_x_spin.valueChanged.connect(self._on_field_setting_changed)
        adv.addRow("Deslocar X (pt):", self.offset_x_spin)

        self.offset_y_spin = QDoubleSpinBox()
        self.offset_y_spin.setRange(-300, 300)
        self.offset_y_spin.setSingleStep(0.5)
        self.offset_y_spin.valueChanged.connect(self._on_field_setting_changed)
        adv.addRow("Deslocar Y (pt):", self.offset_y_spin)

        self.baseline_spin = QDoubleSpinBox()
        self.baseline_spin.setRange(-0.3, 0.3)
        self.baseline_spin.setSingleStep(0.01)
        self.baseline_spin.valueChanged.connect(self._on_field_setting_changed)
        adv.addRow("Linha-base (ems):", self.baseline_spin)

        self.font_override_spin = QDoubleSpinBox()
        self.font_override_spin.setRange(0, 240)
        self.font_override_spin.setSingleStep(0.5)
        self.font_override_spin.setToolTip("0 = automático")
        self.font_override_spin.valueChanged.connect(self._on_field_setting_changed)
        adv.addRow("Tamanho da fonte (0=auto):", self.font_override_spin)

        self.bold_check = QCheckBox("Negrito (apenas CPF/Turma)")
        self.bold_check.toggled.connect(self._on_field_setting_changed)
        adv.addRow(self.bold_check)

        self.consistent_check = QCheckBox("Mesmo tamanho para todos os nomes")
        self.consistent_check.toggled.connect(self._on_field_setting_changed)
        adv.addRow(self.consistent_check)

        layout.addWidget(adv_box)

        # --- Name case ---
        case_box = QGroupBox("Capitalização dos nomes")
        case_layout = QVBoxLayout(case_box)
        self.case_none_radio = QRadioButton("Como na planilha")
        self.case_title_radio = QRadioButton("Capitalizar — ex: João da Silva")
        self.case_upper_radio = QRadioButton("CAIXA ALTA")
        self.case_none_radio.setChecked(True)
        for rb, mode in [(self.case_none_radio, "none"), (self.case_title_radio, "title"),
                          (self.case_upper_radio, "upper")]:
            rb.toggled.connect(lambda checked, m=mode: self._on_name_case_changed(m, checked))
            case_layout.addWidget(rb)
        layout.addWidget(case_box)

        # --- Presets ---
        preset_box = QGroupBox("Predefinições")
        preset_layout = QHBoxLayout(preset_box)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(presets.list_names())
        load_preset_btn = QPushButton("Carregar")
        load_preset_btn.clicked.connect(self._load_preset)
        save_preset_btn = QPushButton("Salvar como...")
        save_preset_btn.clicked.connect(self._save_preset)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(load_preset_btn)
        preset_layout.addWidget(save_preset_btn)
        layout.addWidget(preset_box)

        layout.addStretch()
        self._sync_controls_for_field()
        return scroll

    def _build_canvas_panel(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(8, 8, 8, 8)

        hint = QLabel("Arraste as caixas para reposicionar. Puxe as bordas para redimensionar.")
        hint.setProperty("role", "hint")
        layout.addWidget(hint)

        self.canvas = CanvasEditor()
        self.canvas.field_rect_changed.connect(self._on_canvas_rect_changed)
        self.canvas.active_field_changed.connect(self._on_canvas_active_field_changed)
        layout.addWidget(self.canvas, 1)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Nome de teste:"))
        self.preview_name_edit = QLineEdit(self.preview_name)
        self.preview_name_edit.textChanged.connect(self._on_preview_name_changed)
        preview_row.addWidget(self.preview_name_edit, 1)
        longest_btn = QPushButton("← Maior nome")
        longest_btn.clicked.connect(self._use_longest_name)
        first_btn = QPushButton("1º nome da planilha")
        first_btn.clicked.connect(self._use_first_name)
        preview_row.addWidget(longest_btn)
        preview_row.addWidget(first_btn)
        layout.addLayout(preview_row)

        return wrap

    def _build_right_panel(self) -> QWidget:
        wrap = QWidget()
        wrap.setFixedWidth(340)
        layout = QVBoxLayout(wrap)

        actions_box = QGroupBox("Ações")
        actions = QVBoxLayout(actions_box)

        self.sample_btn = QPushButton("Gerar amostra (3)")
        self.sample_btn.clicked.connect(self.generate_sample)
        actions.addWidget(self.sample_btn)

        self.generate_btn = QPushButton("GERAR CERTIFICADOS")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.clicked.connect(self.generate)
        actions.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton("Cancelar")
        self.cancel_btn.setObjectName("dangerButton")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_generation)
        actions.addWidget(self.cancel_btn)

        self.merge_check = QCheckBox("Juntar tudo em 1 PDF (opcional)")
        self.merge_check.toggled.connect(self._on_merge_toggled)
        actions.addWidget(self.merge_check)

        self.progress_bar = QProgressBar()
        actions.addWidget(self.progress_bar)
        self.progress_detail = QLabel("")
        self.progress_detail.setProperty("role", "hint")
        actions.addWidget(self.progress_detail)

        self.open_folder_btn = QPushButton("📂 Abrir pasta dos certificados")
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self._open_last_outdir)
        actions.addWidget(self.open_folder_btn)

        email_btn = QPushButton("✉ Abrir envio por e-mail")
        email_btn.clicked.connect(self.open_email_window)
        actions.addWidget(email_btn)

        layout.addWidget(actions_box)

        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel, 1)

        self._last_outdir = ""
        return wrap

    def _bind_shortcuts(self):
        def add(seq, slot):
            action = QAction(self)
            action.setShortcut(QKeySequence(seq))
            action.triggered.connect(slot)
            self.addAction(action)

        add("Ctrl+O", self.pick_template)
        add("Ctrl+Shift+O", self.pick_xlsx)
        add("Ctrl+F", self.pick_font)
        add("Ctrl+G", self.generate)
        add("F1", self._show_help)

    # ---------- file pickers ----------

    def pick_template(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolha o PDF do modelo", "", "PDF (*.pdf)")
        if path:
            self.pdf_edit.setText(path)
            self._after_pick_template(path)

    def _after_pick_template(self, path: str):
        self.template_pdf = path
        cfg = load_template_config(path)
        dlg = TemplateFieldsDialog(path, self)
        if cfg:
            for field, cb in dlg.checks.items():
                cb.setChecked(field in cfg.required or field == FIELD_NAME)
        if dlg.exec() != dlg.DialogCode.Accepted:
            required = cfg.required if cfg else [FIELD_NAME]
            fallback_desc = ", ".join(FIELD_TITLES[f] for f in required)
            msgbox.info(
                self, "Seleção de campos cancelada",
                f"Você fechou a janela sem confirmar. Usando: {fallback_desc}.\n\n"
                "Para mudar isso depois, escolha o mesmo PDF novamente em "
                "'Modelo (PDF)' -- a tela de seleção de campos reabre.")
        else:
            required = dlg.required

        try:
            doc = fitz.open(path)
            auto_rects = detect_field_rects_firstpage(doc)
            auto_styles = detect_field_styles_firstpage(doc)
        except Exception as e:
            msgbox.error(self, "PDF", f"Não foi possível abrir o PDF.\n\n{e}")
            return
        finally:
            doc.close()

        fields: Dict[str, FieldCalibration] = dict(cfg.fields) if cfg else {}
        for field in required:
            if field in auto_rects:
                r = auto_rects[field]
                style = auto_styles.get(field, {}) if isinstance(auto_styles, dict) else {}
                fields[field] = FieldCalibration(0, (r.x0, r.y0, r.x1, r.y1), style=style)

        missing = [f for f in required if f not in fields]
        if missing:
            names = ", ".join(FIELD_TITLES[f] for f in missing)
            msgbox.info(
                self, "Calibrar manualmente",
                f"Não encontrei área automática para: {names}.\n\n"
                "Uma caixa provisória foi colocada no centro da página -- arraste-a "
                "no canvas até a posição certa.")
            fallback_doc = fitz.open(path)
            try:
                fallback_rect = compute_auto_area_firstpage(fallback_doc)
            finally:
                fallback_doc.close()
            for f in missing:
                fields[f] = FieldCalibration(0, (fallback_rect.x0, fallback_rect.y0,
                                                  fallback_rect.x1, fallback_rect.y1))

        self.template_cfg = TemplateConfig(required=required, fields=fields, version=3)
        save_template_config(path, self.template_cfg)
        self._apply_bold_from_cfg()
        self._save_current_paths()
        self._refresh_canvas_fields()
        self._request_refresh()

    def pick_xlsx(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolha a planilha (.xlsx)", "", "Excel (*.xlsx)")
        if path:
            self.xlsx_edit.setText(path)
            self._after_pick_xlsx(path)

    def _after_pick_xlsx(self, path: str):
        self.xlsx_path = path
        self.column_mapping = None
        try:
            records = self._read_records()
            self.xlsx_count_label.setText(f"{len(records)} registro(s)")
            if records and (not self.preview_name_edit.text() or self.preview_name_edit.text() == "Seu Nome"):
                self.preview_name_edit.setText(records[0].get(FIELD_NAME, ""))
        except Exception as e:
            self.xlsx_count_label.setText(f"Erro: {e}")
        self._save_current_paths()
        self._request_refresh()

    def _on_header_toggle(self, checked: bool):
        self.xlsx_has_header = checked
        if self.xlsx_path:
            self._after_pick_xlsx(self.xlsx_path)

    def _open_column_mapping(self):
        if not (self.xlsx_path and os.path.isfile(self.xlsx_path)):
            msgbox.info(self, "Planilha", "Escolha primeiro a planilha (.xlsx).")
            return
        headers = sniff_headers(self.xlsx_path)
        default = self.column_mapping or detect_default_mapping(headers)
        dlg = ColumnMappingDialog(headers, default, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self.column_mapping = dlg.mapping()
            self._after_pick_xlsx(self.xlsx_path)

    def pick_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolha a fonte", "", "Fontes (*.ttf *.otf)")
        if path:
            self.font_edit.setText(path)
            self._after_pick_font(path)

    def _after_pick_font(self, path: str):
        try:
            ensure_font_file(path)
            self.font_path = path
        except Exception as e:
            msgbox.warn(self, "Fonte", str(e))
            return
        self._save_current_paths()
        self._request_refresh()

    def pick_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Escolha a pasta onde salvar")
        if d:
            self.output_dir = d
            self.outdir_edit.setText(d)

    def _on_evento_changed(self, text: str):
        self.evento = text

    # ---------- xlsx reading ----------

    def _read_records(self) -> List[Dict[str, str]]:
        if not (self.xlsx_path and os.path.isfile(self.xlsx_path)):
            return []
        if self.column_mapping is not None:
            return read_records_with_mapping(self.xlsx_path, self.column_mapping,
                                              skip_header=self.xlsx_has_header)
        return read_records_from_xlsx(self.xlsx_path, skip_header=self.xlsx_has_header)

    def _use_longest_name(self):
        records = self._read_records()
        if not records:
            msgbox.info(self, "Planilha", "Escolha primeiro a planilha (.xlsx).")
            return
        longest = max((r.get(FIELD_NAME, "") for r in records), key=len)
        self.preview_name_edit.setText(longest)

    def _use_first_name(self):
        records = self._read_records()
        if not records:
            msgbox.info(self, "Planilha", "Escolha primeiro a planilha (.xlsx).")
            return
        self.preview_name_edit.setText(records[0].get(FIELD_NAME, ""))

    # ---------- field editing ----------

    def _on_active_field_radio(self, field: str, checked: bool):
        if checked:
            self.adjust_field = field
            if hasattr(self, "canvas"):
                self.canvas.set_active_field(field)
            if hasattr(self, "snap_check"):
                self._sync_controls_for_field()

    def _on_canvas_active_field_changed(self, field: str):
        if field in self.field_radios:
            self.field_radios[field].setChecked(True)

    def _sync_controls_for_field(self):
        fs = self.field_settings[self.adjust_field]
        for w in (self.snap_check, self.snap_tol_spin, self.offset_x_spin, self.offset_y_spin,
                  self.baseline_spin, self.font_override_spin, self.bold_check, self.consistent_check):
            w.blockSignals(True)
        self.snap_check.setChecked(fs.snap_enabled)
        self.snap_tol_spin.setValue(fs.snap_tol)
        self.offset_x_spin.setValue(fs.offset_x)
        self.offset_y_spin.setValue(fs.offset_y)
        self.baseline_spin.setValue(fs.baseline_tweak_ems)
        self.font_override_spin.setValue(fs.font_override)
        self.bold_check.setChecked(fs.bold)
        self.bold_check.setEnabled(self.adjust_field in (FIELD_CPF, FIELD_TURMA))
        self.consistent_check.setChecked(fs.use_consistent_size)
        self.consistent_check.setVisible(self.adjust_field == FIELD_NAME)
        for w in (self.snap_check, self.snap_tol_spin, self.offset_x_spin, self.offset_y_spin,
                  self.baseline_spin, self.font_override_spin, self.bold_check, self.consistent_check):
            w.blockSignals(False)

    def _on_field_setting_changed(self, *_):
        fs = self.field_settings[self.adjust_field]
        fs.snap_enabled = self.snap_check.isChecked()
        fs.snap_tol = self.snap_tol_spin.value()
        fs.offset_x = self.offset_x_spin.value()
        fs.offset_y = self.offset_y_spin.value()
        fs.baseline_tweak_ems = self.baseline_spin.value()
        fs.font_override = self.font_override_spin.value()
        fs.bold = self.bold_check.isChecked()
        fs.use_consistent_size = self.consistent_check.isChecked()
        if self.template_pdf and self.adjust_field in self.template_cfg.fields:
            style = dict(self.template_cfg.fields[self.adjust_field].style or {})
            style["bold"] = fs.bold
            self.template_cfg.fields[self.adjust_field].style = style
            save_template_config(self.template_pdf, self.template_cfg)
        self._request_refresh()

    def _on_name_case_changed(self, mode: str, checked: bool):
        if checked:
            self.name_case_mode = mode
            self._request_refresh()

    def _on_merge_toggled(self, checked: bool):
        self.merge_pdf = checked

    def _on_preview_name_changed(self, text: str):
        self.preview_name = text
        self._request_refresh()

    def _apply_bold_from_cfg(self):
        for field in ALL_FIELDS:
            style = self.template_cfg.fields.get(field)
            self.field_settings[field].bold = bool(style.style.get("bold", False)) if style and style.style else False

    def _refresh_canvas_fields(self):
        self.canvas.clear_fields()
        for field, calib in self.template_cfg.fields.items():
            if calib.page_index == 0:
                self.canvas.set_field_rect(field, FIELD_TITLES.get(field, field), calib.rect)
        self.canvas.set_active_field(self.adjust_field)

    def _on_canvas_rect_changed(self, field: str, rect: tuple):
        prev_style = None
        if field in self.template_cfg.fields:
            prev_style = self.template_cfg.fields[field].style
        self.template_cfg.fields[field] = FieldCalibration(0, rect, style=prev_style)
        if field not in self.template_cfg.required:
            self.template_cfg.required.append(field)
        if self.template_pdf:
            save_template_config(self.template_pdf, self.template_cfg)
        self._request_refresh()

    # ---------- canvas preview ----------

    def _request_refresh(self):
        self._refresh_timer.start(150)

    def _do_refresh_canvas(self):
        if not (self.template_pdf and os.path.isfile(self.template_pdf)):
            return
        if not (self.font_path and os.path.isfile(self.font_path)):
            return
        try:
            texts = dict(PREVIEW_TEXTS_SAMPLE)
            texts[FIELD_NAME] = apply_name_case(self.preview_name_edit.text() or "Seu Nome",
                                                 self.name_case_mode)

            common_size = None
            if self.field_settings[FIELD_NAME].use_consistent_size:
                records = self._read_records()
                names = [apply_name_case(r.get(FIELD_NAME, ""), self.name_case_mode)
                         for r in records if r.get(FIELD_NAME)]
                if names:
                    from certgen import fonts as fontmod
                    rect = fitz.Rect(*self.template_cfg.fields[FIELD_NAME].rect) \
                        if FIELD_NAME in self.template_cfg.fields else None
                    if rect is not None:
                        common_size = fontmod.common_font_size_for_all(names[:400], rect, self.font_path)

            doc = render_preview_doc(self.template_pdf, self.template_cfg, self.field_settings,
                                      self.font_path, texts, common_name_size=common_size)
            page = doc.load_page(0)
            view_w = max(400, self.canvas.viewport().width())
            scale = max(1.0, min(3.0, view_w / max(1.0, page.rect.width)))
            image = render_page_to_qimage(page, scale)
            self.canvas.set_page_pixmap(image, page.rect.width, page.rect.height)
            doc.close()
            self._refresh_canvas_fields()
        except Exception as e:
            self.log_panel.append(f"Erro na prévia: {e}")

    # ---------- generation ----------

    def _validate_before_generate(self) -> bool:
        if not (self.template_pdf and os.path.isfile(self.template_pdf)):
            msgbox.warn(self, "Atenção", "Escolha o PDF do modelo.")
            return False
        try:
            ensure_font_file(self.font_path)
        except Exception as e:
            msgbox.warn(self, "Fonte", str(e))
            return False
        if not self.evento.strip():
            msgbox.warn(self, "Atenção", "Informe o nome do evento.")
            return False
        return True

    def _build_options(self, sample_limit: Optional[int] = None) -> GenerationOptions:
        return GenerationOptions(
            template_pdf=self.template_pdf, font_path=self.font_path, evento=self.evento,
            output_dir=self.output_dir, merge_pdf=self.merge_pdf,
            name_case_mode=self.name_case_mode, sample_limit=sample_limit,
        )

    def generate_sample(self):
        self._run_generation(sample_limit=3)

    def generate(self):
        if not self._validate_before_generate():
            return
        records = self._read_records()
        if not records:
            msgbox.warn(self, "Atenção", "Nenhum nome encontrado na planilha.")
            return

        if FIELD_CPF in self.template_cfg.required and not any(r.get(FIELD_CPF, "").strip() for r in records):
            msgbox.error(self, "Planilha", "O modelo exige CPF, mas a coluna está vazia.")
            return

        default_turma = ""
        if FIELD_TURMA in self.template_cfg.required and not any(r.get(FIELD_TURMA, "").strip() for r in records):
            val, ok = QInputDialog.getText(self, "Turma", "A planilha não tem Turma. Valor padrão para todos:")
            if not ok:
                return
            default_turma = val.strip()

        name_rect = fitz.Rect(*self.template_cfg.fields[FIELD_NAME].rect) \
            if FIELD_NAME in self.template_cfg.fields else None
        report = run_preflight(records, self.template_cfg.required, name_rect, self.font_path,
                                self.name_case_mode, needs_email=False)
        if report.has_warnings:
            dlg = PreflightDialog(report, self)
            if dlg.exec() != dlg.DialogCode.Accepted or not dlg.proceed:
                return

        options = self._build_options()
        options.default_turma = default_turma
        self._run_generation(options=options, records=records)

    def _run_generation(self, sample_limit: Optional[int] = None,
                         options: Optional[GenerationOptions] = None,
                         records: Optional[List[Dict[str, str]]] = None):
        if not self._validate_before_generate():
            return
        if records is None:
            records = self._read_records()
        if not records:
            msgbox.warn(self, "Atenção", "Nenhum nome encontrado na planilha.")
            return
        if options is None:
            options = self._build_options(sample_limit=sample_limit)

        engine = GenerationEngine(self.template_cfg, self.field_settings, options)
        self.generate_btn.setEnabled(False)
        self.sample_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.log_panel.append("Preparando...")

        self._worker = GenerationWorker(engine, records)
        self._worker.progress.connect(self._on_gen_progress)
        self._worker.log.connect(self.log_panel.append)
        self._worker.finished_ok.connect(self._on_gen_finished)
        self._worker.failed.connect(self._on_gen_failed)
        self._worker.start()

    def cancel_generation(self):
        if self._worker:
            self._worker.cancel()
            self.log_panel.append("Cancelando... aguarde a etapa atual.")

    def _on_gen_progress(self, done: int, total: int):
        pct = int(done * 100 / total) if total else 0
        self.progress_bar.setValue(pct)
        self.progress_detail.setText(f"{done} / {total} ({pct}%)")

    def _on_gen_finished(self, result):
        self.generate_btn.setEnabled(True)
        self.sample_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self._last_outdir = result.outdir
        self.open_folder_btn.setEnabled(True)

        kind = "Amostra" if result.is_sample else "Geração"
        msg = f"{kind} concluída: {result.ok} ok, {result.fail} falha(s).\nPasta: {result.outdir}"
        if result.control_csv_path:
            msg += f"\nControle de envio: {result.control_csv_path}"
        self.log_panel.append(msg.replace("\n", " | "))
        if not result.cancelled:
            msgbox.info(self, "Pronto", msg)
            self._open_folder(result.outdir)

    def _on_gen_failed(self, error: str):
        self.generate_btn.setEnabled(True)
        self.sample_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        msgbox.error(self, "Erro", f"Falha ao gerar: {error}")

    def _open_last_outdir(self):
        self._open_folder(self._last_outdir or self.output_dir or os.getcwd())

    def _open_folder(self, path: str):
        try:
            if os.name == "nt":
                os.startfile(path)
        except Exception as e:
            self.log_panel.append(f"Não foi possível abrir a pasta: {e}")

    # ---------- email ----------

    def open_email_window(self):
        if self._email_window is None:
            self._email_window = EmailWindow(self)
        self._email_window.show()
        self._email_window.raise_()
        self._email_window.activateWindow()

    # ---------- presets ----------

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "Salvar predefinição", "Nome da predefinição:")
        if not ok or not name.strip():
            return
        data = {
            "template_pdf": self.template_pdf, "font_path": self.font_path, "evento": self.evento,
            "output_dir": self.output_dir, "name_case_mode": self.name_case_mode,
            "merge_pdf": self.merge_pdf,
            "field_settings": {f: vars(fs) for f, fs in self.field_settings.items()},
        }
        presets.save_preset(name.strip(), data)
        self.preset_combo.clear()
        self.preset_combo.addItems(presets.list_names())
        self.log_panel.append(f"Predefinição salva: {name.strip()}")

    def _load_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        data = presets.load_preset(name)
        if not data:
            return
        self.template_pdf = data.get("template_pdf", "")
        self.pdf_edit.setText(self.template_pdf)
        self.font_path = data.get("font_path", "")
        self.font_edit.setText(self.font_path)
        self.evento = data.get("evento", self.evento)
        self.evento_combo.setCurrentText(self.evento)
        self.output_dir = data.get("output_dir", "")
        self.outdir_edit.setText(self.output_dir)
        self.name_case_mode = data.get("name_case_mode", "none")
        self.merge_pdf = data.get("merge_pdf", False)
        self.merge_check.setChecked(self.merge_pdf)
        for field, fs_dict in (data.get("field_settings") or {}).items():
            if field in self.field_settings:
                for k, v in fs_dict.items():
                    setattr(self.field_settings[field], k, v)
        if self.template_pdf and os.path.isfile(self.template_pdf):
            cfg = load_template_config(self.template_pdf)
            if cfg:
                self.template_cfg = cfg
        self._sync_controls_for_field()
        self._refresh_canvas_fields()
        self._request_refresh()
        self.log_panel.append(f"Predefinição carregada: {name}")

    # ---------- persistence ----------

    def _load_saved_paths(self):
        p = prefs.load_prefs()
        pdf = p.get("last_pdf", "")
        xlsx = p.get("last_xlsx", "")
        font = p.get("last_font", "")
        if pdf and os.path.isfile(pdf):
            self.pdf_edit.setText(pdf)
            self._after_pick_template(pdf)
        if xlsx and os.path.isfile(xlsx):
            self.xlsx_edit.setText(xlsx)
            self._after_pick_xlsx(xlsx)
        if font and os.path.isfile(font):
            self.font_edit.setText(font)
            self._after_pick_font(font)
        if not p.get("tutorial_shown"):
            self._show_tutorial()
            p["tutorial_shown"] = True
            prefs.save_prefs(p)

    def _save_current_paths(self):
        p = prefs.load_prefs()
        if self.template_pdf:
            p["last_pdf"] = self.template_pdf
        if self.xlsx_path:
            p["last_xlsx"] = self.xlsx_path
        if self.font_path:
            p["last_font"] = self.font_path
        prefs.save_prefs(p)

    def closeEvent(self, event):
        self._save_current_paths()
        super().closeEvent(event)

    # ---------- help ----------

    def _show_help(self):
        msgbox.info(self, "Atalhos",
            "Ctrl+O: Abrir PDF do modelo\n"
            "Ctrl+Shift+O: Abrir planilha (.xlsx)\n"
            "Ctrl+F: Escolher fonte\n"
            "Ctrl+G: Gerar certificados\n\n"
            "No canvas: arraste dentro da caixa para mover, arraste as bordas para "
            "redimensionar, roda do mouse para zoom, botão direito/meio para arrastar a página.")

    def _show_tutorial(self):
        msgbox.info(self, "Guia rápido",
            "1) Modelo (PDF): escolha o certificado.\n"
            "2) Planilha (.xlsx): A=Nome, B=CPF, C=Turma, D=Data, E=Email (ou use "
            "'Mapear colunas...' se sua planilha for diferente).\n"
            "3) Fonte (.ttf/.otf): a fonte usada para escrever os campos.\n"
            "4) No canvas, arraste as caixas para posicionar cada campo -- o que você "
            "vê é exatamente o que será gerado.\n"
            "5) Use 'Gerar amostra (3)' para conferir antes de gerar tudo.\n"
            "6) Gerar: clique em GERAR CERTIFICADOS.\n\n"
            "(Este guia aparece apenas na primeira vez.)")
