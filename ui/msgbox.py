"""
Replacement for QMessageBox's information/warning/critical/question.

Why this exists: QMessageBox has a long-standing Qt bug where, once any
app-wide stylesheet is applied (this app always applies one -- see
ui/theme.py), its internal auto-sizing breaks. The box's private
`_q_updateSize()` recomputes its geometry from the label's word-wrap
BEFORE the label has been given real available width, then resizes the
box to that too-narrow result -- so a multi-line message renders as a
column of near-single-word lines, cut off mid-word. This reproduces with
the static convenience methods AND with an explicitly constructed
QMessageBox with setMinimumWidth() called on it -- the internal resize
logic overrides that too. There is no supported way to fix QMessageBox's
own sizing from outside once a stylesheet is in play.

The fix is to not use QMessageBox at all: a plain QDialog with an
ordinary word-wrapping QLabel behaves like every other normal Qt widget
here, because it has none of QMessageBox's special-cased auto-sizing.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                                QStyle, QVBoxLayout, QWidget)

_MIN_WIDTH = 560
_MAX_WIDTH = 680


def _build(parent: QWidget, title: str, text: str, icon: QStyle.StandardPixmap,
           buttons: QDialogButtonBox.StandardButton) -> QDialog:
    box = QDialog(parent)
    box.setWindowTitle(title)
    box.setMinimumWidth(_MIN_WIDTH)
    box.setMaximumWidth(_MAX_WIDTH)

    root = QVBoxLayout(box)
    row = QHBoxLayout()

    icon_label = QLabel()
    style = box.style()
    pixmap = style.standardIcon(icon).pixmap(32, 32)
    icon_label.setPixmap(pixmap)
    icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
    row.addWidget(icon_label, 0)

    text_label = QLabel(text)
    text_label.setWordWrap(True)
    # A word-wrapping QLabel's sizeHint() uses a heuristic "pleasing
    # aspect ratio" guess at wrap width rather than the space actually
    # available in the dialog, and a mere minimum width still leaves that
    # heuristic in charge of exactly where lines break -- consistently
    # landing just a little too narrow for the dialog's own final size
    # and clipping the last few pixels of the longest lines. A FIXED
    # width sidesteps the heuristic entirely: wrapping happens at
    # exactly this width, full stop, and the dialog's layout sizes
    # itself around that fixed number with nothing left to guess.
    text_label.setFixedWidth(_MIN_WIDTH - 80)
    text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    row.addWidget(text_label, 0)
    root.addLayout(row)

    button_box = QDialogButtonBox(buttons)
    button_box.accepted.connect(box.accept)
    button_box.rejected.connect(box.reject)
    root.addWidget(button_box)

    return box


def info(parent: QWidget, title: str, text: str) -> None:
    box = _build(parent, title, text, QStyle.StandardPixmap.SP_MessageBoxInformation,
                 QDialogButtonBox.StandardButton.Ok)
    box.exec()


def warn(parent: QWidget, title: str, text: str) -> None:
    box = _build(parent, title, text, QStyle.StandardPixmap.SP_MessageBoxWarning,
                 QDialogButtonBox.StandardButton.Ok)
    box.exec()


def error(parent: QWidget, title: str, text: str) -> None:
    box = _build(parent, title, text, QStyle.StandardPixmap.SP_MessageBoxCritical,
                 QDialogButtonBox.StandardButton.Ok)
    box.exec()


def ask_yes_no(parent: QWidget, title: str, text: str) -> bool:
    box = _build(parent, title, text, QStyle.StandardPixmap.SP_MessageBoxQuestion,
                 QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
    return box.exec() == QDialog.DialogCode.Accepted
