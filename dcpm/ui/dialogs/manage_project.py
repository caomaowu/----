from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QRectF
from PyQt6.QtGui import QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, QFileDialog
from qfluentwidgets import (
    SubtitleLabel, LineEdit, StrongBodyLabel, ComboBox, SwitchButton, 
    PushButton, PrimaryPushButton, TextEdit
)

from dcpm.services.library_service import ProjectEntry
from dcpm.ui.theme.colors import COLORS

class ManageProjectDialog(QDialog):
    deleteRequested = pyqtSignal()

    def __init__(self, entry: ProjectEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("管理项目")
        self.setFixedSize(550, 720) 
        self.setStyleSheet(f"background: {COLORS['card']};")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        
        # Title
        layout.addWidget(SubtitleLabel("项目详情", self))
        layout.addSpacing(4)

        # 1. Name
        self._name_edit = LineEdit(self)
        self._name_edit.setText(entry.project.name)
        self._name_edit.setPlaceholderText("项目名称")
        self._add_field(layout, "项目名称", self._name_edit)

        # 1.5 Part Number
        self._part_number_edit = LineEdit(self)
        self._part_number_edit.setText(entry.project.part_number or "")
        self._part_number_edit.setPlaceholderText("料号")
        self._add_field(layout, "料号", self._part_number_edit)

        # 2. Status & Pinned (Row)
        row2 = QHBoxLayout()
        row2.setSpacing(24)
        
        # Status
        self._status_combo = ComboBox(self)
        self._status_combo.addItems(["ongoing", "delivered", "archived"])
        self._status_combo.setCurrentText(entry.project.status)
        self._status_combo.setFixedWidth(200)
        
        status_layout = QVBoxLayout()
        status_layout.setSpacing(8)
        status_layout.addWidget(StrongBodyLabel("状态", self))
        status_layout.addWidget(self._status_combo)
        row2.addLayout(status_layout)
        
        # Pinned
        self._pinned_switch = SwitchButton(self)
        self._pinned_switch.setChecked(entry.pinned)
        self._pinned_switch.setText("置顶显示")
        
        pinned_layout = QVBoxLayout()
        pinned_layout.setSpacing(8)
        pinned_layout.addWidget(StrongBodyLabel("选项", self))
        pinned_layout.addWidget(self._pinned_switch)
        row2.addLayout(pinned_layout)
        
        row2.addStretch()
        layout.addLayout(row2)

        # 3. Cover
        cover_container = QWidget()
        cover_container.setObjectName("coverContainer")
        cover_container.setStyleSheet(f"#coverContainer {{ background: {COLORS['bg']}; border-radius: 8px; border: 1px solid {COLORS['border']}; }}")
        cover_h = QHBoxLayout(cover_container)
        cover_h.setContentsMargins(16, 16, 16, 16)
        
        self._cover_preview = QLabel("无封面")
        self._cover_preview.setFixedSize(160, 90)
        self._cover_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_preview.setStyleSheet(f"background: {COLORS['border']}; border-radius: 6px; color: {COLORS['text_muted']}")
        
        btn_v = QVBoxLayout()
        btn_v.setSpacing(8)
        pick_btn = PushButton("更换封面", self)
        pick_btn.setFixedHeight(32)
        pick_btn.clicked.connect(self._pick_cover)
        clear_btn = PushButton("清除", self)
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear_cover)
        btn_v.addWidget(pick_btn)
        btn_v.addWidget(clear_btn)
        btn_v.addStretch()
        
        cover_h.addWidget(self._cover_preview)
        cover_h.addSpacing(16)
        cover_h.addLayout(btn_v)
        cover_h.addStretch()
        
        self._add_field(layout, "封面图片", cover_container)

        # 4. Tags
        self._tags_edit = LineEdit(self)
        self._tags_edit.setText(",".join(entry.project.tags))
        self._tags_edit.setPlaceholderText("标签用逗号分隔")
        self._add_field(layout, "标签", self._tags_edit)

        # 5. Description
        self._desc_edit = TextEdit(self)
        self._desc_edit.setPlainText(entry.project.description or "")
        self._desc_edit.setPlaceholderText("项目备注...")
        self._desc_edit.setFixedHeight(100)
        self._add_field(layout, "备注", self._desc_edit)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        
        del_btn = PushButton("删除项目", self)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                color: {COLORS['error']}; 
                border: 1px solid {COLORS['border']};
                background: transparent;
            }}
            QPushButton:hover {{
                background: #FEE2E2;
                border: 1px solid #FECACA;
            }}
        """)
        del_btn.clicked.connect(self.deleteRequested.emit)
        
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)

        save_btn = PrimaryPushButton("保存修改", self)
        save_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
        
        # Init state
        self._cover_source_path: str | None = None
        self._cover_cleared = False
        self._apply_existing_cover(entry)

    def _add_field(self, layout, label_text, widget):
        v = QVBoxLayout()
        v.setSpacing(8)
        v.addWidget(StrongBodyLabel(label_text, self))
        v.addWidget(widget)
        layout.addLayout(v)

    def _rounded_pixmap(self, pixmap: QPixmap, w: int, h: int, radius: int) -> QPixmap:
        target = QPixmap(w, h)
        target.fill(Qt.GlobalColor.transparent)

        painter = QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        painter.setClipPath(path)

        scaled = pixmap.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = int((w - scaled.width()) / 2)
        y = int((h - scaled.height()) / 2)
        painter.drawPixmap(x, y, scaled)
        painter.end()
        return target

    def _set_cover_preview_from_file(self, file_path: str) -> None:
        pix = QPixmap(file_path)
        if pix.isNull():
            self._cover_preview.setPixmap(QPixmap())
            self._cover_preview.setText("无法预览")
            return
        self._cover_preview.setText("")
        self._cover_preview.setPixmap(self._rounded_pixmap(pix, 160, 90, 6))

    def _apply_existing_cover(self, entry: ProjectEntry) -> None:
        cover = entry.project.cover_image
        if not cover:
            return
        p = Path(cover)
        if not p.is_absolute():
            p = Path(entry.project_dir) / p
        if p.exists() and p.is_file():
            self._set_cover_preview_from_file(str(p))

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择封面图片",
            "",
            "Images (*.png *.jpg *.jpeg *.webp);;All Files (*.*)",
        )
        if not path:
            return
        self._cover_source_path = path
        self._cover_cleared = False
        self._set_cover_preview_from_file(path)

    def _clear_cover(self) -> None:
        self._cover_source_path = None
        self._cover_cleared = True
        self._cover_preview.setPixmap(QPixmap())
        self._cover_preview.setText("无封面")
    
    @property
    def status(self): return self._status_combo.currentText()
    @property
    def is_pinned(self): return self._pinned_switch.isChecked()
    @property
    def name(self): return self._name_edit.text().strip()
    @property
    def part_number(self): return self._part_number_edit.text().strip() or None
    @property
    def tags_list(self): return self._tags_edit.text().split(",")
    @property
    def description(self): return self._desc_edit.toPlainText()
    @property
    def cover_source_path(self): return self._cover_source_path
    @property
    def cover_cleared(self): return self._cover_cleared
