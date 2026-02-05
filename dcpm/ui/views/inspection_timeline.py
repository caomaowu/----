from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl, QThread
from PyQt6.QtGui import QColor, QPainter, QDesktopServices
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, TransparentToolButton, 
    FluentIcon as FI, CardWidget, InfoBar, StrongBodyLabel, CaptionLabel,
    PillToolButton, IndeterminateProgressRing
)

from dcpm.domain.external_resource import ExternalResource
from dcpm.ui.theme.colors import COLORS
from dcpm.services.scanner_service import (
    get_project_inspections, confirm_inspection_link, remove_inspection_link
)


class InspectionLoader(QThread):
    """异步加载探伤记录的 Worker"""
    loaded = pyqtSignal(list)
    finished_loading = pyqtSignal()
    
    def __init__(self, library_root: Path, project_id: str, limit: int, offset: int):
        super().__init__()
        self.library_root = library_root
        self.project_id = project_id
        self.limit = limit
        self.offset = offset
        
    def run(self):
        # 注意：get_project_inspections 目前是同步的，但在线程中运行不会阻塞 UI。
        # 如果需要分页查询，我们需要修改 service 层或者在这里切片。
        # 考虑到目前 service 层没有分页参数，我们在 Python 层切片。
        # 这对于数千条记录来说，DB 读取还是很快的，主要是 UI 渲染慢。
        # 所以全量读取 + 切片返回是可行的，或者修改 service 支持分页 SQL。
        # 鉴于时间，我们先做内存分页，如果真的很慢再改 SQL。
        
        # 实际上，每次都全量读取不太好。但为了快速实现，我们先这样。
        # 更好的做法是修改 get_project_inspections 支持 LIMIT/OFFSET。
        # 暂时：全量读取，然后切片。
        
        all_resources = get_project_inspections(self.library_root, self.project_id)
        # Filter out ignored
        valid_resources = [r for r in all_resources if r.status != "ignored"]
        
        # Slice
        chunk = valid_resources[self.offset : self.offset + self.limit]
        self.loaded.emit(chunk)
        self.finished_loading.emit()


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
            tag = PillToolButton("已关联", self)
            tag.setIcon(FI.ACCEPT)
            tag.setStyleSheet(f"color: {COLORS['success']}; border: none; background: transparent;")
            tag_layout.addWidget(tag)
        else:
            tag = PillToolButton(f"匹配度: {self.resource.match_score}", self)
            tag.setIcon(FI.QUESTION)
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
        
        # Pagination state
        self.limit = 20
        self.offset = 0
        self.is_loading = False
        self.has_more = True # Optimistic
        self.current_month = None
        
        self.scrollWidget = QWidget()
        self.vBoxLayout = QVBoxLayout(self.scrollWidget)
        
        self.setObjectName("inspectionTimeline")
        self.setStyleSheet("background-color: transparent;")
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        
        self.vBoxLayout.setContentsMargins(32, 20, 32, 20)
        self.vBoxLayout.setSpacing(16)
        
        # Loading Indicator
        self.loading_ring = IndeterminateProgressRing(self.scrollWidget)
        self.loading_ring.setFixedSize(32, 32)
        self.loading_ring.hide()
        
        # Load More Button
        self.load_more_btn = PrimaryPushButton("加载更多", self.scrollWidget)
        self.load_more_btn.clicked.connect(self._load_next_page)
        self.load_more_btn.hide()
        
        self._load_next_page()

    def _load_next_page(self):
        if self.is_loading:
            return
            
        self.is_loading = True
        self.load_more_btn.hide()
        self.loading_ring.show()
        self.loading_ring.start()
        
        # Start Worker
        self.loader = InspectionLoader(self.library_root, self.project_id, self.limit, self.offset)
        self.loader.loaded.connect(self._on_data_loaded)
        self.loader.finished.connect(self._on_loading_finished)
        self.loader.start()

    def _on_data_loaded(self, resources: list[ExternalResource]):
        if not resources:
            self.has_more = False
            if self.offset == 0:
                self._show_empty_state()
            return

        for res in resources:
            # Add Month Header if changed
            month_str = res.folder_date[:7] # YYYY-MM
            if month_str != self.current_month:
                self.current_month = month_str
                header = QLabel(month_str, self.scrollWidget)
                header.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold; font-size: 18px; margin-top: 12px; margin-bottom: 4px;")
                self.vBoxLayout.addWidget(header)
            
            node = TimelineNode(res, self.scrollWidget)
            node.confirmed.connect(self._on_confirmed)
            node.removed.connect(self._on_removed)
            self.vBoxLayout.addWidget(node)
        
        self.offset += len(resources)
        
        # If we got less than limit, we reached the end
        if len(resources) < self.limit:
            self.has_more = False
        else:
            self.has_more = True

    def _on_loading_finished(self):
        self.loading_ring.stop()
        self.loading_ring.hide()
        self.is_loading = False
        
        # Re-add or move Load More button to bottom
        self.vBoxLayout.removeWidget(self.load_more_btn)
        
        if self.has_more:
            self.vBoxLayout.addWidget(self.load_more_btn)
            self.load_more_btn.show()
        else:
            self.vBoxLayout.addStretch()

    def _show_empty_state(self):
        empty_label = QLabel("暂无关联的探伤记录", self.scrollWidget)
        empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; margin-top: 40px;")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.vBoxLayout.addWidget(empty_label)
        self.vBoxLayout.addStretch()

    def reload(self):
        """Reload everything from scratch"""
        self.offset = 0
        self.current_month = None
        self.has_more = True
        
        # Clear layout safely
        while self.vBoxLayout.count():
            item = self.vBoxLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._load_next_page()

    def _on_confirmed(self, resource_id: int):
        confirm_inspection_link(self.library_root, resource_id)
        self.reload()
        InfoBar.success("已确认", "探伤记录已关联", parent=self)

    def _on_removed(self, resource_id: int):
        remove_inspection_link(self.library_root, resource_id)
        self.reload()
        InfoBar.info("已移除", "关联已取消", parent=self)
