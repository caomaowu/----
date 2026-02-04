from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QTimer, QPoint
from PyQt6.QtGui import QFont, QCursor, QPainter, QPainterPath, QPixmap, QColor, QLinearGradient, QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
    QStyleOption,
    QStyle,
    QDialog,
    QScrollArea,
)
from qfluentwidgets import IconWidget, FluentIcon as FI

from dcpm.services.library_service import ProjectEntry
from dcpm.ui.theme.colors import COLORS
from dcpm.ui.components.cards import ShadowCard

@dataclass(frozen=True)
class ProjectCardOptions:
    compact: bool = False


class ProjectCard(ShadowCard):
    """精致的项目卡片"""
    _bg_pixmap_cache: dict[tuple[str, int, int, int], QPixmap] = {}
    _bg_color_cache: dict[tuple[str, int], QColor] = {}

    openRequested = pyqtSignal(object)
    pinToggled = pyqtSignal(str, bool)
    manageRequested = pyqtSignal(object)
    deleteRequested = pyqtSignal(object)
    noteRequested = pyqtSignal(object)

    def __init__(self, entry: ProjectEntry, options: ProjectCardOptions | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._entry = entry
        self._options = options or ProjectCardOptions()
        self._cover_preview_timer: QTimer | None = None
        self._cover_popup: _CoverViewerPopup | None = None
        
        # 基础样式
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(180 if not self._options.compact else 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"""
            ProjectCard {{
                background-color: transparent;
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            }}
            ProjectCard:hover {{
                border: 1px solid {COLORS['primary_light']};
            }}
        """)
        
        self._build()

    def _open_cover_preview(self) -> None:
        self._cover_preview_timer = None
        cover_path = self._cover_path()
        if not cover_path:
            return
        if self._cover_popup is not None and self._cover_popup.isVisible():
            self._cover_popup.close()
            self._cover_popup = None
            return

        popup = _CoverViewerPopup(str(cover_path), title=f"项目封面 · {self._entry.project.name}", parent=self)
        popup.finished.connect(lambda _: setattr(self, "_cover_popup", None))
        self._cover_popup = popup

        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None

        w = popup.width()
        h = popup.height()

        if geo:
            x = cursor.x() - int(w * 0.5)
            y = cursor.y() - int(h * 0.55)
            x = max(geo.left() + 12, min(x, geo.right() - w - 12))
            y = max(geo.top() + 12, min(y, geo.bottom() - h - 12))
            popup.move(x, y)
        else:
            popup.move(cursor + QPoint(12, 12))

        popup.show()
        popup.activateWindow()

    def _cover_path(self) -> Path | None:
        cover = self._entry.project.cover_image
        if not cover:
            return None
        p = Path(cover)
        if not p.is_absolute():
            p = Path(self._entry.project_dir) / p
        if p.exists() and p.is_file():
            return p
        return None

    @classmethod
    def _cache_put(cls, cache: dict, key, value, limit: int) -> None:
        cache[key] = value
        while len(cache) > limit:
            try:
                cache.pop(next(iter(cache)))
            except Exception:
                break

    @classmethod
    def _get_cover_mtime(cls, path: Path) -> int:
        try:
            return int(path.stat().st_mtime)
        except Exception:
            return 0

    @classmethod
    def _get_scaled_cover_pixmap(cls, path: Path, w: int, h: int) -> QPixmap | None:
        mtime = cls._get_cover_mtime(path)
        key = (str(path), mtime, int(w), int(h))
        cached = cls._bg_pixmap_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached

        pix = QPixmap(str(path))
        if pix.isNull():
            return None

        scaled = pix.scaled(
            int(w),
            int(h),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        cls._cache_put(cls._bg_pixmap_cache, key, scaled, limit=160)
        return scaled

    @classmethod
    def _get_cover_avg_color(cls, path: Path) -> QColor:
        mtime = cls._get_cover_mtime(path)
        key = (str(path), mtime)
        cached = cls._bg_color_cache.get(key)
        if cached is not None:
            return cached

        pix = QPixmap(str(path))
        if pix.isNull():
            c = QColor(COLORS["primary_light"])
            cls._cache_put(cls._bg_color_cache, key, c, limit=240)
            return c

        img = pix.toImage()
        if img.isNull():
            c = QColor(COLORS["primary_light"])
            cls._cache_put(cls._bg_color_cache, key, c, limit=240)
            return c

        small = img.scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        c = small.pixelColor(0, 0)
        cls._cache_put(cls._bg_color_cache, key, c, limit=240)
        return c

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        radius = 12.0
        r = QRectF(self.rect())

        clip = QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        painter.setClipPath(clip)

        card_color = QColor(COLORS["card"])
        painter.fillPath(clip, card_color)

        cover_path = self._cover_path()
        if cover_path:
            if self._options.compact:
                strip_w = 10
                c = self._get_cover_avg_color(cover_path)
                grad = QLinearGradient(0, 0, 0, r.height())
                top = QColor(c)
                top.setAlpha(230)
                bottom = QColor(c)
                bottom.setAlpha(190)
                grad.setColorAt(0.0, top)
                grad.setColorAt(1.0, bottom)
                painter.fillRect(0, 0, strip_w, int(r.height()), grad)
            else:
                scaled = self._get_scaled_cover_pixmap(cover_path, int(r.width()), int(r.height()))
                if scaled is not None and not scaled.isNull():
                    x = int((r.width() - scaled.width()) / 2)
                    y = int((r.height() - scaled.height()) / 2)
                    painter.drawPixmap(x, y, scaled)

                    frosted = QColor(255, 255, 255, 135)
                    painter.fillRect(self.rect(), frosted)

                    grad = QLinearGradient(r.left(), r.top(), r.right(), r.top())
                    grad.setColorAt(0.0, QColor(255, 255, 255, 200))
                    grad.setColorAt(0.55, QColor(255, 255, 255, 110))
                    grad.setColorAt(1.0, QColor(255, 255, 255, 10))
                    painter.fillRect(self.rect(), grad)

        painter.setClipping(False)

        option = QStyleOption()
        option.initFrom(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if isinstance(child, QPushButton):
                super().mousePressEvent(event)
                return

            if self._cover_path():
                if self._cover_preview_timer is None:
                    self._cover_preview_timer = QTimer(self)
                    self._cover_preview_timer.setSingleShot(True)
                    self._cover_preview_timer.timeout.connect(self._open_cover_preview)
                self._cover_preview_timer.start(220)

        super().mousePressEvent(event)

    def _build(self) -> None:
        if self._options.compact:
            self._build_compact()
        else:
            self._build_grid()

    def _build_grid(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        
        # 顶部：图标和编号
        top_layout = QHBoxLayout()
        
        # 渐变背景图标
        icon_container = QWidget()
        icon_container.setFixedSize(48, 48)
        icon_container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {COLORS['primary_light']},
                    stop:1 {COLORS['primary']});
                border-radius: 12px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon = IconWidget(FI.FOLDER)
        icon.setFixedSize(24, 24)
        icon.setStyleSheet("color: white;")
        icon_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
        
        top_layout.addWidget(icon_container)
        
        # 编号与客户
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(2)
        
        code_label = QLabel(self._entry.project.id)
        code_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        code_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px; font-weight: bold;")
        meta_layout.addWidget(code_label)
        
        cust_label = QLabel(self._entry.project.customer)
        cust_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        cust_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        meta_layout.addWidget(cust_label)
        
        top_layout.addLayout(meta_layout)
        top_layout.addStretch()
        
        # 操作按钮
        pin_btn = QPushButton("★" if self._entry.pinned else "☆")
        pin_btn.setFixedSize(28, 28)
        pin_btn.setCheckable(True)
        pin_btn.setChecked(self._entry.pinned)
        pin_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                color: {COLORS['warning'] if self._entry.pinned else COLORS['text_muted']};
                font-size: 16px;
                background: transparent;
            }}
            QPushButton:hover {{ background: {COLORS['bg']}; border-radius: 4px; }}
        """)
        pin_btn.toggled.connect(lambda v: self.pinToggled.emit(self._entry.project.id, v))
        top_layout.addWidget(pin_btn)

        manage_btn = QPushButton()
        manage_btn.setIcon(FI.EDIT.icon())
        manage_btn.setFixedSize(28, 28)
        manage_btn.setToolTip("管理项目")
        manage_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
            }}
            QPushButton:hover {{ background: {COLORS['bg']}; border-radius: 4px; }}
        """)
        manage_btn.clicked.connect(lambda: self.manageRequested.emit(self._entry))
        top_layout.addWidget(manage_btn)

        # Note Button
        note_btn = QPushButton()
        note_btn.setIcon(FI.CHAT.icon())
        note_btn.setFixedSize(28, 28)
        note_btn.setToolTip("项目留言")
        note_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
            }}
            QPushButton:hover {{ background: {COLORS['bg']}; border-radius: 4px; }}
        """)
        note_btn.clicked.connect(lambda: self.noteRequested.emit(self._entry))
        top_layout.addWidget(note_btn)
        
        # 删除按钮
        del_btn = QPushButton()
        del_btn.setIcon(FI.DELETE.icon())
        del_btn.setFixedSize(28, 28)
        del_btn.setToolTip("删除项目")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
            }}
            QPushButton:hover {{ background: #fee2e2; border-radius: 4px; }}
        """)
        del_btn.clicked.connect(lambda: self.deleteRequested.emit(self._entry))
        top_layout.addWidget(del_btn)
        
        layout.addLayout(top_layout)
        
        # 项目名称
        name_label = QLabel(self._entry.project.name)
        name_font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        name_label.setFont(name_font)
        name_label.setWordWrap(True)
        name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_label.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(name_label)
        
        # 标签
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)
        for tag in self._entry.project.tags[:3]:
            lbl = QLabel(f"#{tag}")
            lbl.setStyleSheet(f"""
                background: {COLORS['bg']}; 
                color: {COLORS['text_muted']};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            """)
            tags_layout.addWidget(lbl)
        tags_layout.addStretch()
        layout.addLayout(tags_layout)
        
        layout.addStretch()
        
        # 底部：时间和打开按钮
        bottom_layout = QHBoxLayout()
        dt = self._entry.project.create_time.strftime("%Y-%m-%d")
        date_label = QLabel(dt)
        date_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        date_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        bottom_layout.addWidget(date_label)
        
        bottom_layout.addStretch()
        
        open_btn = QPushButton("打开")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setFixedHeight(26)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 13px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['primary']};
                color: white;
                border: 1px solid {COLORS['primary']};
            }}
        """)
        open_btn.clicked.connect(lambda: self.openRequested.emit(self._entry))
        bottom_layout.addWidget(open_btn)
        
        layout.addLayout(bottom_layout)

    def _build_compact(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)
        
        icon = IconWidget(FI.FOLDER)
        icon.setFixedSize(20, 20)
        icon.setStyleSheet(f"color: {COLORS['primary']};")
        layout.addWidget(icon)
        
        # 信息列
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        name_label = QLabel(self._entry.project.name)
        name_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        name_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {COLORS['text']};")
        info_layout.addWidget(name_label)
        
        meta = f"{self._entry.project.id} · {self._entry.project.customer}"
        meta_label = QLabel(meta)
        meta_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        meta_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        info_layout.addWidget(meta_label)
        
        layout.addLayout(info_layout, 1)
        
        # 标签
        for tag in self._entry.project.tags[:2]:
            lbl = QLabel(f"#{tag}")
            lbl.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; background: {COLORS['bg']}; padding: 2px 4px; border-radius: 4px;")
            layout.addWidget(lbl)
            
        # 按钮组
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        
        pin_btn = QPushButton("★" if self._entry.pinned else "☆")
        pin_btn.setFixedSize(24, 24)
        pin_btn.setCheckable(True)
        pin_btn.setChecked(self._entry.pinned)
        pin_btn.setStyleSheet(f"border: none; color: {COLORS['warning'] if self._entry.pinned else COLORS['text_muted']}; background: transparent;")
        pin_btn.toggled.connect(lambda v: self.pinToggled.emit(self._entry.project.id, v))
        btn_layout.addWidget(pin_btn)
        
        manage_btn = QPushButton()
        manage_btn.setIcon(FI.EDIT.icon())
        manage_btn.setFixedSize(24, 24)
        manage_btn.setStyleSheet("border: none; background: transparent;")
        manage_btn.clicked.connect(lambda: self.manageRequested.emit(self._entry))
        btn_layout.addWidget(manage_btn)
        
        open_btn = QPushButton("打开")
        open_btn.setFixedHeight(24)
        open_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 0 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {COLORS['border']}; }}
        """)
        open_btn.clicked.connect(lambda: self.openRequested.emit(self._entry))
        btn_layout.addWidget(open_btn)
        
        layout.addLayout(btn_layout)

    def mouseDoubleClickEvent(self, event):
        if self._cover_preview_timer is not None:
            self._cover_preview_timer.stop()
        self.openRequested.emit(self._entry)


class _CoverViewerDialog(QDialog):
    def __init__(self, image_path: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 680)
        self.setStyleSheet(f"background: {COLORS['card']};")

        self._pix = QPixmap(image_path)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.addWidget(self._label, 1)
        self._scroll.setWidget(container)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._scroll)

        self._refresh()

    def _refresh(self) -> None:
        if self._pix.isNull():
            self._label.setText("无法加载图片")
            self._label.setPixmap(QPixmap())
            return
        viewport = self._scroll.viewport().size()
        w = max(1, viewport.width() - 32)
        h = max(1, viewport.height() - 32)
        scaled = self._pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._label.setText("")
        self._label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()


class _CoverViewerPopup(_CoverViewerDialog):
    def __init__(self, image_path: str, title: str, parent: QWidget | None = None):
        super().__init__(image_path, title=title, parent=parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(
            f"background: {COLORS['card']}; border: 1px solid {COLORS['border']}; border-radius: 12px;"
        )
        self.resize(900, 620)
        self._refresh()

    def mousePressEvent(self, event) -> None:
        self.close()
        super().mousePressEvent(event)
