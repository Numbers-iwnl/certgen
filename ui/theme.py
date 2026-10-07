"""Visual identity, kept consistent with the baseline app's teal palette
so the rewrite doesn't feel like a different product to people who
already know it."""

C_BG = "#eef8f4"
C_PRIMARY = "#17c88b"
C_TEAL = "#009475"
C_DARK = "#002927"
C_WARM = "#3a3530"
C_BORDER = "#d6e7e2"
C_SURFACE = "#ffffff"
C_MUTED = "#6b6b6b"
C_DANGER = "#c0392b"
C_WARNING = "#a3760a"
C_OK = "#117a54"

STYLESHEET = f"""
* {{
    font-family: "Segoe UI", sans-serif;
    font-size: 10.5pt;
}}
QWidget {{
    background: {C_BG};
    color: {C_WARM};
}}
QLabel, QCheckBox, QRadioButton {{
    background: transparent;
}}
QMainWindow, QDialog {{
    background: {C_BG};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {C_BG};
    border: none;
}}
QTableWidget, QListWidget, QPlainTextEdit, QTextEdit {{
    background: {C_SURFACE};
}}
QWidget#headerBand {{
    background: {C_PRIMARY};
}}
QLabel#headerTitle {{
    color: white;
    font-size: 13pt;
    font-weight: 600;
    padding-left: 4px;
}}
QLabel#headerVersion {{
    color: rgba(255,255,255,0.85);
    font-size: 9pt;
}}
QGroupBox {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px;
    font-weight: 600;
    color: {C_DARK};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {C_TEAL};
}}
QLabel {{
    color: {C_WARM};
}}
QLabel[role="hint"] {{
    color: {C_MUTED};
    font-size: 9pt;
}}
QLabel[role="error"] {{
    color: {C_DANGER};
}}
QLabel[role="ok"] {{
    color: {C_OK};
}}
QPushButton {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 5px;
    padding: 6px 14px;
    color: {C_DARK};
}}
QPushButton:hover {{
    border-color: {C_PRIMARY};
}}
QPushButton:pressed {{
    background: {C_BORDER};
}}
QPushButton:disabled {{
    color: #a9a9a9;
    background: #f2f2f2;
}}
QPushButton#primaryButton {{
    background: {C_PRIMARY};
    color: white;
    font-weight: 600;
    border: none;
    padding: 10px 18px;
    font-size: 11.5pt;
    border-radius: 6px;
}}
QPushButton#primaryButton:hover {{
    background: {C_TEAL};
}}
QPushButton#primaryButton:disabled {{
    background: #bdbdbd;
}}
QPushButton#dangerButton {{
    color: {C_DANGER};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background: {C_SURFACE};
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    color: {C_DARK};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {C_PRIMARY};
}}
QCheckBox, QRadioButton {{
    color: {C_WARM};
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid #b9c9c4;
    background: {C_SURFACE};
}}
QCheckBox::indicator {{
    border-radius: 3px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border: 1px solid {C_PRIMARY};
}}
QCheckBox::indicator:checked {{
    background: {C_PRIMARY};
    border: 1px solid {C_TEAL};
    image: none;
}}
QRadioButton::indicator:checked {{
    background: {C_SURFACE};
    border: 4px solid {C_PRIMARY};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: #eeeeee;
    border-color: #d5d5d5;
}}
QProgressBar {{
    border: 1px solid {C_BORDER};
    border-radius: 4px;
    background: {C_SURFACE};
    text-align: center;
    height: 18px;
}}
QProgressBar::chunk {{
    background: {C_PRIMARY};
    border-radius: 3px;
}}
QTabWidget::pane {{
    border: 1px solid {C_BORDER};
    background: {C_SURFACE};
}}
QTabBar::tab {{
    background: {C_BG};
    padding: 6px 14px;
    border: 1px solid {C_BORDER};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {C_SURFACE};
    color: {C_TEAL};
    font-weight: 600;
}}
QTableWidget {{
    background: {C_SURFACE};
    gridline-color: {C_BORDER};
    border: 1px solid {C_BORDER};
}}
QHeaderView::section {{
    background: {C_BG};
    color: {C_DARK};
    padding: 4px;
    border: none;
    border-bottom: 1px solid {C_BORDER};
    font-weight: 600;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QGraphicsView {{
    background: #d9e4e1;
    border: 1px solid {C_BORDER};
}}
QPlainTextEdit#logPanel {{
    background: #0f1b19;
    color: #d6f5ea;
    font-family: Consolas, monospace;
    font-size: 9pt;
}}
QToolTip {{
    background: #fffbe6;
    color: #333;
    border: 1px solid {C_BORDER};
    padding: 4px;
}}
"""
