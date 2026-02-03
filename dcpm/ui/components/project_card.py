from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from qfluentwidgets import IconWidget, FluentIcon as FI

from dcpm.services.library_service import ProjectEntry
from dcpm.ui.theme.colors import COLORS
from dcpm.ui.components.cards import ShadowCard

@dataclass(frozen=True)
class ProjectCardOptions:
    compact: bool = False


class ProjectCard(ShadowCard):
    """精致的项目卡片"""
    openRequested = pyqtSignal(object)
    pinToggled = pyqtSignal(str, bool)
    manageRequested = pyqtSignal(object)
    deleteRequested = pyqtSignal(object)

    def __init__(self, entry: ProjectEntry, options: ProjectCardOptions | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._entry = entry
        self._options = options or ProjectCardOptions()
        
        # 基础样式
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(180 if not self._options.compact else 80)
        self.setStyleSheet(f"""
            ProjectCard {{
                background-color: {COLORS['card']};
                border-radius: 12px;
                border: 1px solid {COLORS['border']};
            }}
            ProjectCard:hover {{
                border: 1px solid {COLORS['primary_light']};
            }}
        """)
        
        self._build()

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
        code_label.setStyleSheet(f"color: {COLORS['primary']}; font-size: 11px; font-weight: bold;")
        meta_layout.addWidget(code_label)
        
        cust_label = QLabel(self._entry.project.customer)
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
        
        # 小图标
        icon = IconWidget(FI.FOLDER)
        icon.setFixedSize(20, 20)
        icon.setStyleSheet(f"color: {COLORS['primary']};")
        layout.addWidget(icon)
        
        # 信息列
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        name_label = QLabel(self._entry.project.name)
        name_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {COLORS['text']};")
        info_layout.addWidget(name_label)
        
        meta = f"{self._entry.project.id} · {self._entry.project.customer}"
        meta_label = QLabel(meta)
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
        self.openRequested.emit(self._entry)
