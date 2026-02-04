from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl
from PyQt6.QtGui import QColor, QPainter, QDesktopServices
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, TransparentToolButton, 
    FluentIcon as FI, CardWidget, InfoBar, StrongBodyLabel, CaptionLabel,
    PillToolButton
)

from dcpm.domain.external_resource import ExternalResource
from dcpm.ui.theme.colors import COLORS
from dcpm.services.scanner_service import (
    get_project_inspections, confirm_inspection_link, remove_inspection_link
)


class TimelineNode(CardWidget):
    """时间轴节点卡片"""
    
    confirmed = pyqtSignal(int)
    removed = pyqtSignal(int)

    def __init__(self, resource: ExternalResource, parent=None):
        super().__init__(parent)
        self.resource = resource
        self.setupUI()

    def setupUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        # 1. Date & Status Indicator
        date_col = QVBoxLayout()
        date_col.setSpacing(4)
        
        # Month-Day
        date_label = StrongBodyLabel(self.resource.folder_date[5:], self) # MM-DD
        date_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 16px;")
        date_col.addWidget(date_label)
        
        # Year
        year_label = CaptionLabel(str(self.resource.folder_year), self)
        year_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        date_col.addWidget(year_label)
        
        layout.addLayout(date_col)

        # Vertical Separator / Status Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        if self.resource.status == "confirmed":
            line.setStyleSheet(f"color: {COLORS['success']}; background-color: {COLORS['success']}; border: 2px solid {COLORS['success']};")
        else:
            line.setStyleSheet(f"color: {COLORS['warning']}; background-color: {COLORS['warning']}; border: 2px solid {COLORS['warning']};")
        line.setFixedWidth(4)
        layout.addWidget(line)

        # 2. Folder Info
        info_col = QVBoxLayout()
        info_col.setSpacing(6)
        
        folder_label = StrongBodyLabel(self.resource.folder_name, self)
        info_col.addWidget(folder_label)
        
        path_label = CaptionLabel(self.resource.full_path, self)
        path_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        path_label.setWordWrap(True)
        info_col.addWidget(path_label)
        
        # Tags/Score
        tag_layout = QHBoxLayout()
        tag_layout.setSpacing(8)
        
        if self.resource.status == "confirmed":
            tag = PillToolButton(FI.ACCEPT, "已关联", self)
            tag.setDisabled(True) # Just as a badge
            tag.setStyleSheet(f"color: {COLORS['success']}; border: none; background: transparent;")
            tag_layout.addWidget(tag)
        else:
            tag = PillToolButton(FI.QUESTION, f"匹配度: {self.resource.match_score}", self)
            tag.setDisabled(True)
            tag.setStyleSheet(f"color: {COLORS['warning']}; border: none; background: transparent;")
            tag_layout.addWidget(tag)

        tag_layout.addStretch()
        info_col.addLayout(tag_layout)
        
        layout.addLayout(info_col, stretch=1)

        # 3. Actions
        action_col = QVBoxLayout()
        action_col.setSpacing(8)
        
        open_btn = TransparentToolButton(FI.FOLDER, self)
        open_btn.setToolTip("打开文件夹")
        open_btn.clicked.connect(self._open_folder)
        action_col.addWidget(open_btn)

        if self.resource.status == "pending":
            confirm_btn = TransparentToolButton(FI.ACCEPT, self)
            confirm_btn.setToolTip("确认关联")
            confirm_btn.setStyleSheet(f"color: {COLORS['success']}")
            confirm_btn.clicked.connect(lambda: self.confirmed.emit(self.resource.id))
            action_col.addWidget(confirm_btn)
            
            remove_btn = TransparentToolButton(FI.CLOSE, self)
            remove_btn.setToolTip("忽略此推荐")
            remove_btn.setStyleSheet(f"color: {COLORS['error']}")
            remove_btn.clicked.connect(lambda: self.removed.emit(self.resource.id))
            action_col.addWidget(remove_btn)
        elif self.resource.status == "confirmed":
            # Allow removing confirmation
            remove_btn = TransparentToolButton(FI.CLOSE, self)
            remove_btn.setToolTip("取消关联")
            remove_btn.clicked.connect(lambda: self.removed.emit(self.resource.id))
            action_col.addWidget(remove_btn)

        action_col.addStretch()
        layout.addLayout(action_col)

    def _open_folder(self):
        path = self.resource.full_path
        try:
            # Use explorer /select if possible, or just open
            os.startfile(path)
        except Exception as e:
            # Fallback
            subprocess.Popen(f'explorer "{path}"')


class InspectionTimeline(ScrollArea):
    """探伤记录时间轴视图"""

    def __init__(self, library_root: Path, project_id: str, parent=None):
        super().__init__(parent)
        self.library_root = library_root
        self.project_id = project_id
        
        self.scrollWidget = QWidget()
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        
        self.setObjectName("inspectionTimeline")
        self.setStyleSheet("background-color: transparent;")
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        
        self.vBoxLayout.setContentsMargins(32, 20, 32, 20)
        self.vBoxLayout.setSpacing(16)
        
        self.load_data()

    def load_data(self):
        # Clear existing
        while self.vBoxLayout.count():
            item = self.vBoxLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        resources = get_project_inspections(self.library_root, self.project_id)
        
        # Filter out ignored
        resources = [r for r in resources if r.status != "ignored"]
        
        if not resources:
            empty_label = QLabel("暂无关联的探伤记录", self.scrollWidget)
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; margin-top: 40px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.vBoxLayout.addWidget(empty_label)
            return

        # Group by Month? Or just list sorted by date (already sorted by SQL)
        current_month = None
        
        for res in resources:
            # Add Month Header if changed
            month_str = res.folder_date[:7] # YYYY-MM
            if month_str != current_month:
                current_month = month_str
                header = QLabel(month_str, self.scrollWidget)
                header.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold; font-size: 18px; margin-top: 12px; margin-bottom: 4px;")
                self.vBoxLayout.addWidget(header)
            
            node = TimelineNode(res, self.scrollWidget)
            node.confirmed.connect(self._on_confirmed)
            node.removed.connect(self._on_removed)
            self.vBoxLayout.addWidget(node)

        self.vBoxLayout.addStretch()

    def _on_confirmed(self, resource_id: int):
        confirm_inspection_link(self.library_root, resource_id)
        self.load_data()
        InfoBar.success("已确认", "探伤记录已关联", parent=self)

    def _on_removed(self, resource_id: int):
        remove_inspection_link(self.library_root, resource_id)
        self.load_data()
        InfoBar.info("已移除", "关联已取消", parent=self)
