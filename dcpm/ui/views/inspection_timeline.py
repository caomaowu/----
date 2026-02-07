from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QUrl, QThread, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, 
    QSizePolicy, QCompleter
)
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, TransparentToolButton, 
    FluentIcon as FI, CardWidget, InfoBar, StrongBodyLabel, CaptionLabel,
    PillToolButton, IndeterminateProgressRing, SearchLineEdit, ComboBox,
    SubtitleLabel, ToolButton, ToggleToolButton, IconWidget
)

from dcpm.domain.external_resource import ExternalResource
from dcpm.ui.theme.colors import COLORS
from dcpm.services.scanner_service import (
    get_project_inspections, confirm_inspection_link, remove_inspection_link
)


def elide_path(path_str: str, max_chars: int = 60) -> str:
    """智能截断长路径"""
    if len(path_str) <= max_chars:
        return path_str
    
    # 保留头部和尾部
    # e.g. \\192.168.1.1\...\2025\1-2
    head_len = 20
    tail_len = max_chars - head_len - 3 # 3 for '...'
    
    return f"{path_str[:head_len]}...{path_str[-tail_len:]}"


class InspectionLoader(QThread):
    """异步加载探伤记录的 Worker (全量加载)"""
    loaded = pyqtSignal(list)
    
    def __init__(self, library_root: Path, project_id: str):
        super().__init__()
        self.library_root = library_root
        self.project_id = project_id
        
    def run(self):
        # 全量读取，由 UI 层进行过滤和渲染优化
        all_resources = get_project_inspections(self.library_root, self.project_id)
        # Filter out ignored immediately
        valid_resources = [r for r in all_resources if r.status != "ignored"]
        # Sort by date desc
        valid_resources.sort(key=lambda r: r.folder_date, reverse=True)
        
        self.loaded.emit(valid_resources)


class InspectionToolbar(QWidget):
    """顶部筛选工具栏"""
    filterChanged = pyqtSignal() # 当任何筛选条件变化时触发
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(16, 10, 16, 10)
        self.layout.setSpacing(12)
        
        # 1. Search Box
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索文件夹名称或路径...")
        self.search_edit.setFixedWidth(260)
        self.search_edit.textChanged.connect(self.filterChanged)
        self.layout.addWidget(self.search_edit)
        
        # 2. Status Filter
        self.status_combo = ComboBox(self)
        self.status_combo.addItems(["全部状态", "待确认", "已关联"])
        self.status_combo.setFixedWidth(120)
        self.status_combo.currentTextChanged.connect(self.filterChanged)
        self.layout.addWidget(self.status_combo)
        
        # 3. Year Filter (Populated dynamically)
        self.year_combo = ComboBox(self)
        self.year_combo.addItem("所有年份")
        self.year_combo.setFixedWidth(120)
        self.year_combo.currentTextChanged.connect(self._on_year_changed)
        self.layout.addWidget(self.year_combo)
        
        # 4. Month Filter
        self.month_combo = ComboBox(self)
        self.month_combo.addItem("所有月份")
        self.month_combo.setFixedWidth(120)
        self.month_combo.currentTextChanged.connect(self.filterChanged)
        self.layout.addWidget(self.month_combo)
        
        self.layout.addStretch()
        
    def get_search_text(self) -> str:
        return self.search_edit.text().strip().lower()
        
    def get_status_filter(self) -> str:
        text = self.status_combo.currentText()
        if text == "待确认": return "pending"
        if text == "已关联": return "confirmed"
        return "all"
        
    def get_year_filter(self) -> str:
        return self.year_combo.currentText()
    
    def get_month_filter(self) -> str:
        text = self.month_combo.currentText()
        if text == "所有月份":
            return "all"
        return text.replace("月", "") # "01月" -> "01"
        
    def set_years(self, years: List[int]):
        current = self.year_combo.currentText()
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItem("所有年份")
        for y in sorted(years, reverse=True):
            self.year_combo.addItem(str(y))
        
        if current in [str(y) for y in years] or current == "所有年份":
            self.year_combo.setCurrentText(current)
        self.year_combo.blockSignals(False)
        
        # Trigger month update
        self._on_year_changed(self.year_combo.currentText())

    def _on_year_changed(self, year_text: str):
        # Update months based on logic (currently just show all months, 
        # but could be filtered by available data if we had it here)
        # For simplicity, just reset to All and show 1-12
        current_month = self.month_combo.currentText()
        self.month_combo.blockSignals(True)
        self.month_combo.clear()
        self.month_combo.addItem("所有月份")
        for m in range(1, 13):
            self.month_combo.addItem(f"{m:02d}月")
            
        if current_month != "所有月份":
            # Try to keep selection
            self.month_combo.setCurrentText(current_month)
            
        self.month_combo.blockSignals(False)
        self.filterChanged.emit()


class TimelineNode(CardWidget):
    """重构后的时间轴节点卡片"""
    
    confirmed = pyqtSignal(int)
    removed = pyqtSignal(int)
    browseRequested = pyqtSignal(str)

    def __init__(self, resource: ExternalResource, parent=None):
        super().__init__(parent)
        self.resource = resource
        self.setFixedHeight(80) # 固定高度，更紧凑
        self.setupUI()

    def setupUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        # 1. Date Block (Left)
        date_col = QVBoxLayout()
        date_col.setSpacing(0)
        date_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Day (e.g. "03")
        try:
            day_str = self.resource.folder_date.split("-")[2]
            month_str = self.resource.folder_date.split("-")[1] + "月"
        except IndexError:
            day_str = "??"
            month_str = "??"
            
        day_label = QLabel(day_str, self)
        day_label.setStyleSheet(f"color: {COLORS['text']}; font-size: 24px; font-weight: bold;")
        day_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_col.addWidget(day_label)
        
        # Month (e.g. "12月") - 小字
        month_label = CaptionLabel(month_str, self)
        month_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        date_col.addWidget(month_label)
        
        layout.addLayout(date_col)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {COLORS['border']}; border: 1px solid {COLORS['border']};")
        layout.addWidget(line)

        # 2. Main Info (Middle)
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # Title Row: Name + Status Pill
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        
        name_label = SubtitleLabel(self.resource.folder_name, self)
        title_row.addWidget(name_label)
        
        if self.resource.status == "confirmed":
            tag = PillToolButton("已关联", self)
            tag.setIcon(FI.ACCEPT)
            tag.setChecked(True) # Solid color style
            tag.setStyleSheet(f"background-color: {COLORS['success']}; color: white; border: none;")
            title_row.addWidget(tag)
        else:
            tag = PillToolButton(f"匹配度: {self.resource.match_score}", self)
            tag.setIcon(FI.QUESTION)
            tag.setStyleSheet(f"color: {COLORS['warning']}; border: 1px solid {COLORS['warning']}; background: transparent;")
            title_row.addWidget(tag)
            
        title_row.addStretch()
        info_col.addLayout(title_row)
        
        # Path Row
        full_path = self.resource.full_path
        short_path = elide_path(full_path)
        path_label = CaptionLabel(short_path, self)
        path_label.setToolTip(full_path)
        path_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        info_col.addWidget(path_label)
        
        layout.addLayout(info_col, stretch=1)

        # 3. Actions (Right)
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        
        browse_btn = TransparentToolButton(FI.VIEW, self)
        browse_btn.setToolTip("在应用内浏览")
        browse_btn.clicked.connect(lambda: self.browseRequested.emit(self.resource.full_path))
        action_row.addWidget(browse_btn)
        
        open_btn = TransparentToolButton(FI.FOLDER, self)
        open_btn.setToolTip("打开文件夹")
        open_btn.clicked.connect(self._open_folder)
        action_row.addWidget(open_btn)

        if self.resource.status == "pending":
            confirm_btn = TransparentToolButton(FI.ACCEPT, self)
            confirm_btn.setToolTip("确认关联")
            confirm_btn.setIconSize(QSize(18, 18))
            confirm_btn.setStyleSheet(f"color: {COLORS['success']}")
            confirm_btn.clicked.connect(lambda: self.confirmed.emit(self.resource.id))
            action_row.addWidget(confirm_btn)
            
            remove_btn = TransparentToolButton(FI.CLOSE, self)
            remove_btn.setToolTip("忽略")
            remove_btn.setIconSize(QSize(18, 18))
            remove_btn.setStyleSheet(f"color: {COLORS['error']}")
            remove_btn.clicked.connect(lambda: self.removed.emit(self.resource.id))
            action_row.addWidget(remove_btn)
        elif self.resource.status == "confirmed":
            remove_btn = TransparentToolButton(FI.CLOSE, self)
            remove_btn.setToolTip("取消关联")
            remove_btn.clicked.connect(lambda: self.removed.emit(self.resource.id))
            action_row.addWidget(remove_btn)

        layout.addLayout(action_row)

    def _open_folder(self):
        path = self.resource.full_path
        try:
            os.startfile(path)
        except Exception:
            subprocess.Popen(f'explorer "{path}"')


class MonthGroupWidget(QWidget):
    """按月分组的折叠容器 (UI Fix: Prevent overlapping)"""
    
    def __init__(self, month_str: str, count: int, parent=None):
        super().__init__(parent)
        self.month_str = month_str
        self.is_expanded = False
        
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(0, 0, 0, 0)
        self.v_layout.setSpacing(0)
        
        # Header Button (Custom implementation to fix layout issues)
        self.header_btn = QPushButton(self)
        self.header_btn.setFixedHeight(40)
        self.header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background: transparent;
                text-align: left;
                padding-left: 0px;
            }}
            QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.03);
                border-radius: 4px;
            }}
        """)
        self.header_btn.clicked.connect(self.toggle)
        
        # Internal layout for the button
        self.header_layout = QHBoxLayout(self.header_btn)
        self.header_layout.setContentsMargins(4, 0, 4, 0)
        self.header_layout.setSpacing(8)
        
        # Icon
        self.icon_widget = IconWidget(FI.CHEVRON_RIGHT_MED, self.header_btn)
        self.icon_widget.setFixedSize(16, 16)
        # Apply primary color to icon
        # IconWidget doesn't easily take stylesheet color, need to use QPainter or specific method if available.
        # But FluentIcon usually handles color via theme. Let's force it if needed, or just leave default.
        # Actually IconWidget has `setIcon` but color is tricky.
        # Let's use a simple QLabel for icon if IconWidget is troublesome, but IconWidget is standard.
        
        self.header_layout.addWidget(self.icon_widget)
        
        # Text
        self.title_label = QLabel(f"{month_str} ({count})", self.header_btn)
        self.title_label.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold; font-size: 16px;")
        self.header_layout.addWidget(self.title_label)
        
        self.header_layout.addStretch()
        
        self.v_layout.addWidget(self.header_btn)
        
        # Content Container
        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 0, 8, 16) # Indent content
        self.content_layout.setSpacing(8)
        self.content_widget.hide() # Default hidden
        self.v_layout.addWidget(self.content_widget)
        
    def add_node(self, node: TimelineNode):
        self.content_layout.addWidget(node)
        
    def toggle(self):
        self.is_expanded = not self.is_expanded
        if self.is_expanded:
            self.content_widget.show()
            self.icon_widget.setIcon(FI.CHEVRON_DOWN_MED)
        else:
            self.content_widget.hide()
            self.icon_widget.setIcon(FI.CHEVRON_RIGHT_MED)
            
    def expand(self):
        if not self.is_expanded:
            self.toggle()


class InspectionTimeline(QWidget):
    """探伤记录主视图 (Toolbar + ScrollArea)"""
    
    browseRequested = pyqtSignal(str)

    def __init__(self, library_root: Path, project_id: str, parent=None):
        super().__init__(parent)
        self.library_root = library_root
        self.project_id = project_id
        
        self.all_resources: List[ExternalResource] = []
        self.displayed_resources: List[ExternalResource] = []
        
        # Main Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 1. Toolbar
        self.toolbar = InspectionToolbar(self)
        self.toolbar.filterChanged.connect(self._apply_filters)
        self.main_layout.addWidget(self.toolbar)
        
        # 2. Scroll Area
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(24, 10, 24, 24)
        self.scroll_layout.setSpacing(16)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        self.main_layout.addWidget(self.scroll_area)
        
        # Loading Indicator (Overlay)
        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(48, 48)
        self.loading_ring.hide()
        
        # Initial Load
        self._load_data()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_ring.move(
            self.width() // 2 - self.loading_ring.width() // 2,
            self.height() // 2 - self.loading_ring.height() // 2
        )

    def _load_data(self):
        self.loading_ring.show()
        self.loading_ring.start()
        self.scroll_widget.hide()
        
        self.loader = InspectionLoader(self.library_root, self.project_id)
        self.loader.loaded.connect(self._on_data_loaded)
        self.loader.start()

    def _on_data_loaded(self, resources: list[ExternalResource]):
        self.loading_ring.stop()
        self.loading_ring.hide()
        self.scroll_widget.show()
        
        self.all_resources = resources
        
        # Populate Year Filter
        years = set()
        for r in resources:
            years.add(r.folder_year)
        self.toolbar.set_years(list(years))
        
        # Apply Filters (will render)
        self._apply_filters()

    def _apply_filters(self):
        search_text = self.toolbar.get_search_text()
        status_filter = self.toolbar.get_status_filter()
        year_filter = self.toolbar.get_year_filter()
        month_filter = self.toolbar.get_month_filter()
        
        filtered = []
        for res in self.all_resources:
            # 1. Search
            if search_text:
                if search_text not in res.folder_name.lower() and search_text not in res.full_path.lower():
                    continue
            
            # 2. Status
            if status_filter != "all":
                if res.status != status_filter:
                    continue
            
            # 3. Year
            if year_filter != "所有年份":
                if str(res.folder_year) != year_filter:
                    continue
            
            # 4. Month
            if month_filter != "all":
                # res.folder_date is YYYY-MM-DD
                # extract MM
                try:
                    res_month = res.folder_date.split("-")[1]
                    if res_month != month_filter:
                        continue
                except IndexError:
                    continue
            
            filtered.append(res)
            
        self.displayed_resources = filtered
        self._render_list()

    def _render_list(self):
        # Clear existing
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.displayed_resources:
            empty_label = QLabel("没有找到匹配的探伤记录", self.scroll_widget)
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; margin-top: 40px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.scroll_layout.addWidget(empty_label)
            return

        # Group by Month
        groups = {} # "YYYY-MM" -> [resources]
        months_order = []
        
        for res in self.displayed_resources:
            month = res.folder_date[:7] # YYYY-MM
            if month not in groups:
                groups[month] = []
                months_order.append(month)
            groups[month].append(res)
            
        # Render Groups
        for i, month in enumerate(months_order):
            res_list = groups[month]
            group_widget = MonthGroupWidget(month, len(res_list), self.scroll_widget)
            
            for res in res_list:
                node = TimelineNode(res)
                node.confirmed.connect(self._on_confirmed)
                node.removed.connect(self._on_removed)
                node.browseRequested.connect(self.browseRequested)
                group_widget.add_node(node)
            
            self.scroll_layout.addWidget(group_widget)
            
            # Auto-expand the first group (latest month)
            if i == 0:
                group_widget.expand()
        
        self.scroll_layout.addStretch()

    def reload(self):
        self._load_data()

    def _on_confirmed(self, resource_id: int):
        confirm_inspection_link(self.library_root, resource_id)
        # Refresh locally to avoid full reload flicker? 
        # Ideally update local object status and re-filter.
        # But for safety, reload data to sync with DB.
        # To make it smoother, we could just update self.all_resources
        
        for i, r in enumerate(self.all_resources):
            if r.id == resource_id:
                self.all_resources[i] = replace(r, status="confirmed")
                break
        
        InfoBar.success("已确认", "探伤记录已关联", parent=self)
        self._apply_filters()

    def _on_removed(self, resource_id: int):
        remove_inspection_link(self.library_root, resource_id)
        
        # Remove from local list
        self.all_resources = [r for r in self.all_resources if r.id != resource_id]
        
        InfoBar.info("已移除", "关联已取消", parent=self)
        self._apply_filters()
