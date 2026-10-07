"""
The Phase 3 centerpiece: direct manipulation of field placement on a live
render of the actual certificate, replacing the baseline's disconnected
flow (a modal rectangle-selector, closed, then blind spinbox nudging
while watching a separate preview pane).

Design choice: the scene's coordinate system IS the PDF page's point
space (fitz.Rect coordinates), 1:1. The QGraphicsView's own zoom
transform handles on-screen scale, so every field box's QRectF is always
exactly the calibrated rect -- no separate pixel<->point conversion
bookkeeping. The background is the real rendered certificate (via the
same certgen.render draw functions used for actual generation), so what
the user sees IS what will be produced -- including where snap actually
puts the text, not just where the box was dragged to.
"""
from typing import Dict, Optional, Tuple

import pymupdf as fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                                QGraphicsSimpleTextItem, QGraphicsView)

FIELD_COLORS = {
    "name": "#17c88b",
    "cpf": "#3a86ff",
    "date": "#ff9f1c",
    "turma": "#e0479e",
}

_HANDLE_MARGIN = 8  # view pixels
_MIN_RECT_SIZE = 12.0  # pt


class _FieldBox(QGraphicsRectItem):
    def __init__(self, field: str, title: str, rect: QRectF):
        super().__init__(rect)
        self.field = field
        color = QColor(FIELD_COLORS.get(field, "#17c88b"))
        pen = QPen(color, 0)  # cosmetic pen: constant 1px regardless of zoom
        pen.setCosmetic(True)
        pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 35)))
        self.setZValue(10)

        self.label = QGraphicsSimpleTextItem(title, self)
        self.label.setBrush(QBrush(color))
        f = self.label.font()
        f.setBold(True)
        f.setPointSizeF(8)
        self.label.setFont(f)
        self.label.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._position_label()

    def setRect(self, rect: QRectF):
        super().setRect(rect)
        self._position_label()

    def _position_label(self):
        r = self.rect()
        self.label.setPos(r.x(), r.y() - 2)


class CanvasEditor(QGraphicsView):
    field_rect_changed = Signal(str, tuple)  # field, (x0,y0,x1,y1) in pt
    active_field_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._bg_item: Optional[QGraphicsPixmapItem] = None
        self._boxes: Dict[str, _FieldBox] = {}
        self._page_size: Tuple[float, float] = (595.0, 842.0)
        self._active_field: Optional[str] = None

        self._drag_mode: Optional[str] = None  # None|"move"|"n"|"s"|"e"|"w"|"ne"|...
        self._drag_field: Optional[str] = None
        self._drag_start_scene: QPointF = QPointF()
        self._drag_start_rect: QRectF = QRectF()

        self._zoom = 1.0
        self.setMouseTracking(True)

    # ---------- public API ----------

    def set_page_pixmap(self, image: QImage, page_width: float, page_height: float):
        self._page_size = (page_width, page_height)
        if self._bg_item is None:
            self._bg_item = QGraphicsPixmapItem()
            self._bg_item.setZValue(0)
            self._scene.addItem(self._bg_item)
        pixmap = QPixmap.fromImage(image)
        self._bg_item.setPixmap(pixmap)
        if pixmap.width() > 0:
            self._bg_item.setScale(page_width / pixmap.width())
        self._scene.setSceneRect(0, 0, page_width, page_height)
        for box in self._boxes.values():
            box.setZValue(10)

    def set_field_rect(self, field: str, title: str, rect_pt: Tuple[float, float, float, float]):
        qrect = QRectF(rect_pt[0], rect_pt[1], rect_pt[2] - rect_pt[0], rect_pt[3] - rect_pt[1])
        if field in self._boxes:
            self._boxes[field].setRect(qrect)
        else:
            box = _FieldBox(field, title, qrect)
            self._scene.addItem(box)
            self._boxes[field] = box

    def remove_field(self, field: str):
        box = self._boxes.pop(field, None)
        if box is not None:
            self._scene.removeItem(box)

    def clear_fields(self):
        for f in list(self._boxes.keys()):
            self.remove_field(f)

    def set_active_field(self, field: Optional[str]):
        self._active_field = field
        for f, box in self._boxes.items():
            pen = box.pen()
            pen.setWidth(3 if f == field else 0)
            pen.setStyle(Qt.SolidLine if f == field else Qt.DashLine)
            box.setPen(pen)
            box.setZValue(20 if f == field else 10)

    def fit_page(self):
        if self._bg_item is not None:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()

    # ---------- zoom / pan ----------

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.1, min(8.0, self._zoom * factor))
        self.setTransform(self.transform().fromScale(self._zoom, self._zoom))
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._bg_item is not None:
            self.fit_page()

    # ---------- direct manipulation ----------

    def _hit_test(self, box: _FieldBox, scene_pos: QPointF) -> Optional[str]:
        rect = box.rect()
        view_rect_topleft = self.mapFromScene(rect.topLeft())
        view_rect_botright = self.mapFromScene(rect.bottomRight())
        view_pos = self.mapFromScene(scene_pos)

        margin = _HANDLE_MARGIN
        near_left = abs(view_pos.x() - view_rect_topleft.x()) <= margin
        near_right = abs(view_pos.x() - view_rect_botright.x()) <= margin
        near_top = abs(view_pos.y() - view_rect_topleft.y()) <= margin
        near_bottom = abs(view_pos.y() - view_rect_botright.y()) <= margin

        inside_x = view_rect_topleft.x() - margin <= view_pos.x() <= view_rect_botright.x() + margin
        inside_y = view_rect_topleft.y() - margin <= view_pos.y() <= view_rect_botright.y() + margin
        if not (inside_x and inside_y):
            return None

        vert = "n" if near_top else ("s" if near_bottom else "")
        horiz = "w" if near_left else ("e" if near_right else "")
        combo = vert + horiz
        if combo:
            return combo
        if rect.contains(scene_pos):
            return "move"
        return None

    def _cursor_for_mode(self, mode: str):
        mapping = {
            "move": Qt.CursorShape.SizeAllCursor,
            "n": Qt.CursorShape.SizeVerCursor, "s": Qt.CursorShape.SizeVerCursor,
            "e": Qt.CursorShape.SizeHorCursor, "w": Qt.CursorShape.SizeHorCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor, "sw": Qt.CursorShape.SizeBDiagCursor,
            "nw": Qt.CursorShape.SizeFDiagCursor, "se": Qt.CursorShape.SizeFDiagCursor,
        }
        return mapping.get(mode, Qt.CursorShape.ArrowCursor)

    def _topmost_box_at(self, scene_pos: QPointF) -> Optional[_FieldBox]:
        # active field first, so overlapping boxes prefer whichever the user is editing
        ordered = sorted(self._boxes.values(), key=lambda b: 0 if b.field == self._active_field else 1)
        for box in ordered:
            if self._hit_test(box, scene_pos):
                return box
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            box = self._topmost_box_at(scene_pos)
            if box is not None:
                mode = self._hit_test(box, scene_pos)
                self._drag_mode = mode
                self._drag_field = box.field
                self._drag_start_scene = scene_pos
                self._drag_start_rect = QRectF(box.rect())
                self.active_field_changed.emit(box.field)
                event.accept()
                return
        elif event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            fake = event
            super().mousePressEvent(fake)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode and self._drag_field:
            scene_pos = self.mapToScene(event.pos())
            dx = scene_pos.x() - self._drag_start_scene.x()
            dy = scene_pos.y() - self._drag_start_scene.y()
            r = QRectF(self._drag_start_rect)

            if self._drag_mode == "move":
                r.translate(dx, dy)
            else:
                if "n" in self._drag_mode:
                    r.setTop(min(r.top() + dy, r.bottom() - _MIN_RECT_SIZE))
                if "s" in self._drag_mode:
                    r.setBottom(max(r.bottom() + dy, r.top() + _MIN_RECT_SIZE))
                if "w" in self._drag_mode:
                    r.setLeft(min(r.left() + dx, r.right() - _MIN_RECT_SIZE))
                if "e" in self._drag_mode:
                    r.setRight(max(r.right() + dx, r.left() + _MIN_RECT_SIZE))

            page_w, page_h = self._page_size
            r = r.normalized()
            r.setLeft(max(0.0, r.left()))
            r.setTop(max(0.0, r.top()))
            r.setRight(min(page_w, r.right()))
            r.setBottom(min(page_h, r.bottom()))

            self._boxes[self._drag_field].setRect(r)
            event.accept()
            return

        # hover feedback
        scene_pos = self.mapToScene(event.pos())
        box = self._topmost_box_at(scene_pos)
        if box is not None:
            mode = self._hit_test(box, scene_pos)
            self.setCursor(QCursor(self._cursor_for_mode(mode or "")))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_mode and self._drag_field:
            box = self._boxes[self._drag_field]
            r = box.rect()
            self.field_rect_changed.emit(self._drag_field, (r.left(), r.top(), r.right(), r.bottom()))
            self._drag_mode = None
            self._drag_field = None
            event.accept()
            return
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        super().mouseReleaseEvent(event)


def render_page_to_qimage(page: fitz.Page, target_scale: float) -> QImage:
    """Rasterize a fitz page to a QImage at the given px-per-point scale."""
    pix = page.get_pixmap(matrix=fitz.Matrix(target_scale, target_scale), alpha=False)
    fmt = QImage.Format.Format_RGB888
    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
    return image.copy()  # detach from PyMuPDF's buffer before it's freed
