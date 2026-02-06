from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QSizePolicy
)
from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, TransparentToolButton,
    FluentIcon as FI, CardWidget, InfoBar, StrongBodyLabel, CaptionLabel,
    SearchLineEdit, ComboBox, SubtitleLabel, PillToolButton,
    IndeterminateProgressRing, ToolButton
)

from dcpm.domain.shared_drive_file import SharedDriveFolder, FolderStatus
from dcpm.ui.theme.colors import COLORS
from dcpm.services.shared_drive_service import SharedDriveService


class FolderLoader(QThread):
    """异步加载共享盘文件夹的 Worker"""
    loaded = pyqtSignal(list)
    
    def __init__(self, library_root: Path, project_id: str):
        super().__init__()
        self.library_root = library_root
        self.project_id = project_id
        
    def run(self):
        service = SharedDriveService(self.library_root)
        folders = service.get_project_folders(self.project_id)
        # 过滤掉已忽略的
        valid_folders = [f for f in folders if f.status != FolderStatus.IGNORED]
        # 按修改时间降序
        valid_folders.sort(key=lambda f: f.modified_time, reverse=True)
        self.loaded.emit(valid_folders)


class ScanWorker(QThread):
    """异步扫描共享盘的 Worker"""
    finished = pyqtSignal(int)
    progress = pyqtSignal(str)
    
    def __init__(self, library_root: Path, shared_drive_path: str, project_id: str):
        super().__init__()
        self.library_root = library_root
        self.shared_drive_path = shared_drive_path
        self.project_id = project_id
        
    def run(self):
        from dcpm.infra.fs.metadata import load_project
        
        # 加载项目信息
        project = load_project(self.library_root, self.project_id)
        if not project:
            self.finished.emit(0)
            return
        
        from dcpm.services.shared_drive_service import quick_scan_project
        count = quick_scan_project(
            self.library_root,
            self.shared_drive_path,
            project
        )
        self.finished.emit(count)


class FolderToolbar(QWidget):
    """顶部工具栏"""
    filterChanged = pyqtSignal()
    scanRequested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(16, 10, 16, 10)
        self.layout.setSpacing(12)
        
        # 搜索框
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("搜索文件夹...")
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self.filterChanged)
        self.layout.addWidget(self.search_edit)
        
        # 状态筛选
        self.status_combo = ComboBox(self)
        self.status_combo.addItems(["全部状态", "已索引", "已确认"])
        self.status_combo.setFixedWidth(100)
        self.status_combo.currentTextChanged.connect(self.filterChanged)
        self.layout.addWidget(self.status_combo)
        
        self.layout.addStretch()
        
        # 扫描按钮
        self.scan_btn = PrimaryPushButton(FI.SYNC, "扫描共享盘", self)
        self.scan_btn.setFixedHeight(32)
        self.scan_btn.clicked.connect(self.scanRequested)
        self.layout.addWidget(self.scan_btn)
    
    def get_search_text(self) -> str:
        return self.search_edit.text().strip().lower()
    
    def get_status_filter(self) -> str | None:
        text = self.status_combo.currentText()
        if text == "已索引":
            return "indexed"
        elif text == "已确认":
            return "confirmed"
        return None


class FolderNode(CardWidget):
    """文件夹节点卡片"""
    confirmed = pyqtSignal(int)
    ignored = pyqtSignal(int)
    unconfirmed = pyqtSignal(int)  # 取消确认
    deleted = pyqtSignal(int)      # 删除索引
    opened = pyqtSignal(str)  # 发送完整路径
    
    def __init__(self, folder: SharedDriveFolder, root_path: str, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.root_path = root_path
        self.setFixedHeight(70)
        self.setupUI()
    
    def setupUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)
        
        # 左侧：文件夹图标
        icon_col = QVBoxLayout()
        icon_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel("📁", self)
        icon_label.setStyleSheet("font-size: 24px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_col.addWidget(icon_label)
        layout.addLayout(icon_col)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet(f"color: {COLORS['border']};")
        layout.addWidget(line)
        
        # 中间：文件夹信息
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        
        # 文件夹名行
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        
        name_label = SubtitleLabel(self.folder.folder_name, self)
        name_label.setToolTip(self.folder.folder_path)
        name_row.addWidget(name_label)
        
        # 状态标签
        if self.folder.status == FolderStatus.CONFIRMED:
            status_tag = PillToolButton("已确认", self)
            status_tag.setIcon(FI.ACCEPT)
            status_tag.setChecked(True)
            status_tag.setStyleSheet(f"background-color: {COLORS['success']}; color: white; border: none;")
        else:
            status_tag = PillToolButton(f"匹配度: {self.folder.match_score}", self)
            status_tag.setIcon(FI.LINK)
            status_tag.setStyleSheet(f"color: {COLORS['info']}; border: 1px solid {COLORS['info']}; background: transparent;")
        name_row.addWidget(status_tag)
        name_row.addStretch()
        info_col.addLayout(name_row)
        
        # 路径和统计行
        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        
        path_label = CaptionLabel(self.folder.folder_path, self)
        path_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        meta_row.addWidget(path_label)
        
        meta_row.addStretch()
        
        # 显示文件数量和大小
        stats_text = f"{self.folder.file_count} 个文件 | {self.folder.size_human}"
        stats_label = CaptionLabel(stats_text, self)
        stats_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        meta_row.addWidget(stats_label)
        
        time_str = self.folder.modified_time.strftime("%m-%d %H:%M")
        time_label = CaptionLabel(time_str, self)
        time_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        meta_row.addWidget(time_label)
        
        info_col.addLayout(meta_row)
        layout.addLayout(info_col, stretch=1)
        
        # 右侧：操作按钮
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        
        open_btn = TransparentToolButton(FI.FOLDER, self)
        open_btn.setToolTip("打开文件夹")
        open_btn.clicked.connect(self._open_folder)
        action_row.addWidget(open_btn)
        
        if self.folder.status == FolderStatus.CONFIRMED:
            # 已确认的文件夹：显示取消确认和删除索引按钮
            unconfirm_btn = TransparentToolButton(FI.CANCEL, self)
            unconfirm_btn.setToolTip("取消确认")
            unconfirm_btn.setIconSize(QSize(18, 18))
            unconfirm_btn.setStyleSheet(f"color: {COLORS['warning']}")
            unconfirm_btn.clicked.connect(lambda: self.unconfirmed.emit(self.folder.id))
            action_row.addWidget(unconfirm_btn)
            
            delete_btn = TransparentToolButton(FI.DELETE, self)
            delete_btn.setToolTip("删除索引")
            delete_btn.setIconSize(QSize(18, 18))
            delete_btn.setStyleSheet(f"color: {COLORS['error']}")
            delete_btn.clicked.connect(lambda: self.deleted.emit(self.folder.id))
            action_row.addWidget(delete_btn)
        else:
            # 未确认的文件夹：显示确认和忽略按钮
            confirm_btn = TransparentToolButton(FI.ACCEPT, self)
            confirm_btn.setToolTip("确认关联")
            confirm_btn.setIconSize(QSize(18, 18))
            confirm_btn.setStyleSheet(f"color: {COLORS['success']}")
            confirm_btn.clicked.connect(lambda: self.confirmed.emit(self.folder.id))
            action_row.addWidget(confirm_btn)
            
            ignore_btn = TransparentToolButton(FI.CLOSE, self)
            ignore_btn.setToolTip("忽略")
            ignore_btn.setIconSize(QSize(18, 18))
            ignore_btn.setStyleSheet(f"color: {COLORS['error']}")
            ignore_btn.clicked.connect(lambda: self.ignored.emit(self.folder.id))
            action_row.addWidget(ignore_btn)
        
        layout.addLayout(action_row)
    
    def _open_folder(self):
        # 使用文件夹自己的 root_path
        root_path = self.folder.root_path
        
        if not root_path:
            InfoBar.warning(
                title="无法打开文件夹",
                content="未配置共享盘路径，请在设置中配置",
                parent=self
            )
            return
        
        full_path = Path(root_path) / self.folder.folder_path
        if full_path.exists():
            try:
                os.startfile(str(full_path))
            except Exception:
                try:
                    subprocess.Popen(f'explorer "{full_path}"')
                except Exception as e:
                    InfoBar.error(
                        title="打开文件夹失败",
                        content=str(e),
                        parent=self
                    )
        else:
            InfoBar.warning(
                title="文件夹不存在",
                content=f"路径: {full_path}",
                parent=self
            )


class EmptyWidget(QWidget):
    """空状态提示"""
    def __init__(self, message: str = "暂无数据", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel("📂", self)
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        msg_label = QLabel(message, self)
        msg_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; margin-top: 12px;")
        msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg_label)


class SharedDriveBrowser(QWidget):
    """共享盘文件夹浏览器主视图"""
    
    def __init__(
        self,
        library_root: Path,
        project_id: str,
        shared_drive_path: str | None = None,
        parent=None
    ):
        super().__init__(parent)
        self.library_root = library_root
        self.project_id = project_id
        self.shared_drive_path = shared_drive_path or ""
        
        self.all_folders: List[SharedDriveFolder] = []
        self.displayed_folders: List[SharedDriveFolder] = []
        
        self.service = SharedDriveService(library_root)
        
        self.setupUI()
        self.load_data()
    
    def setupUI(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 工具栏
        self.toolbar = FolderToolbar(self)
        self.toolbar.filterChanged.connect(self.apply_filters)
        self.toolbar.scanRequested.connect(self.start_scan)
        self.main_layout.addWidget(self.toolbar)
        
        # 统计栏
        self.stats_label = QLabel(self)
        self.stats_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px; padding: 4px 16px;")
        self.main_layout.addWidget(self.stats_label)
        
        # 滚动区域
        self.scroll_area = ScrollArea(self)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(16, 8, 16, 16)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        self.main_layout.addWidget(self.scroll_area)
        
        # 加载动画
        self.loading_ring = IndeterminateProgressRing(self)
        self.loading_ring.setFixedSize(48, 48)
        self.loading_ring.hide()
        
        # 空状态
        self.empty_widget = EmptyWidget('点击右上角"扫描共享盘"开始索引文件夹', self)
        self.empty_widget.hide()
        self.main_layout.addWidget(self.empty_widget)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.loading_ring.move(
            self.width() // 2 - self.loading_ring.width() // 2,
            self.height() // 2 - self.loading_ring.height() // 2
        )
    
    def load_data(self):
        """加载文件夹数据"""
        self.loading_ring.show()
        self.loading_ring.start()
        self.scroll_widget.hide()
        
        self.loader = FolderLoader(self.library_root, self.project_id)
        self.loader.loaded.connect(self.on_data_loaded)
        self.loader.start()
    
    def on_data_loaded(self, folders: List[SharedDriveFolder]):
        self.loading_ring.stop()
        self.loading_ring.hide()
        self.scroll_widget.show()
        
        self.all_folders = folders
        
        # 更新统计
        self.update_stats()
        
        # 应用筛选并渲染
        self.apply_filters()
        
        # 如果没有数据，显示空状态
        if not folders and not self.shared_drive_path:
            self.scroll_widget.hide()
            self.empty_widget.show()
    
    def update_stats(self):
        """更新统计信息"""
        total = len(self.all_folders)
        confirmed = sum(1 for f in self.all_folders if f.status == FolderStatus.CONFIRMED)
        total_size = sum(f.total_size for f in self.all_folders)
        
        # 格式化总大小
        size_str = ""
        if total_size < 1024 * 1024:
            size_str = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / (1024 * 1024 * 1024):.1f} GB"
        
        self.stats_label.setText(f"共 {total} 个文件夹 | 已确认 {confirmed} 个 | 总计 {size_str}")
    
    def apply_filters(self):
        """应用筛选条件"""
        search_text = self.toolbar.get_search_text()
        status_filter = self.toolbar.get_status_filter()
        
        filtered = []
        for f in self.all_folders:
            # 搜索筛选
            if search_text:
                if search_text not in f.folder_name.lower() and search_text not in f.folder_path.lower():
                    continue
            
            # 状态筛选
            if status_filter and f.status.value != status_filter:
                continue
            
            filtered.append(f)
        
        self.displayed_folders = filtered
        self.render_list()
    
    def render_list(self):
        """渲染文件夹列表"""
        # 清除旧内容
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self.displayed_folders:
            empty_label = QLabel("没有找到匹配的文件夹", self.scroll_widget)
            empty_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px; margin-top: 40px;")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.scroll_layout.addWidget(empty_label)
            return
        
        # 渲染文件夹节点
        for folder in self.displayed_folders:
            node = FolderNode(folder, self.shared_drive_path, self.scroll_widget)
            node.confirmed.connect(self.on_confirmed)
            node.ignored.connect(self.on_ignored)
            node.unconfirmed.connect(self.on_unconfirmed)
            node.deleted.connect(self.on_deleted)
            self.scroll_layout.addWidget(node)
        
        self.scroll_layout.addStretch()
    
    def start_scan(self):
        """开始扫描共享盘"""
        if not self.shared_drive_path:
            # 尝试从设置获取
            from dcpm.infra.config.user_config import load_user_config
            cfg = load_user_config()
            self.shared_drive_path = getattr(cfg, 'shared_drive_path', '')
        
        if not self.shared_drive_path:
            InfoBar.warning(
                title="未配置共享盘路径",
                content="请在设置中配置共享盘路径",
                parent=self
            )
            return
        
        self.toolbar.scan_btn.setEnabled(False)
        self.toolbar.scan_btn.setText("扫描中...")
        
        self.scan_worker = ScanWorker(
            self.library_root,
            self.shared_drive_path,
            self.project_id
        )
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.start()
    
    def on_scan_finished(self, count: int):
        """扫描完成回调"""
        self.toolbar.scan_btn.setEnabled(True)
        self.toolbar.scan_btn.setText("扫描共享盘")
        
        InfoBar.success(
            title="扫描完成",
            content=f"共索引 {count} 个文件夹",
            parent=self
        )
        
        # 重新加载数据
        self.empty_widget.hide()
        self.load_data()
    
    def on_confirmed(self, folder_id: int):
        """确认文件夹关联"""
        self.service.confirm_folder(folder_id)
        
        # 更新本地状态，不重新加载
        self._update_folder_status(folder_id, FolderStatus.CONFIRMED)
        InfoBar.success("已确认", "文件夹关联已确认", parent=self)
    
    def on_ignored(self, folder_id: int):
        """忽略文件夹"""
        self.service.ignore_folder(folder_id)
        
        # 从列表中移除，不重新加载
        self.all_folders = [f for f in self.all_folders if f.id != folder_id]
        self.displayed_folders = [f for f in self.displayed_folders if f.id != folder_id]
        InfoBar.info("已忽略", "文件夹已从列表中移除", parent=self)
        self.update_stats()
        self.render_list()
    
    def on_unconfirmed(self, folder_id: int):
        """取消确认文件夹关联"""
        self.service.unconfirm_folder(folder_id)
        
        # 更新本地状态，不重新加载
        self._update_folder_status(folder_id, FolderStatus.INDEXED)
        InfoBar.info("已取消确认", "文件夹已回到已索引状态", parent=self)
    
    def on_deleted(self, folder_id: int):
        """删除文件夹索引"""
        self.service.delete_folder_index(folder_id)
        
        # 从列表中移除，不重新加载
        self.all_folders = [f for f in self.all_folders if f.id != folder_id]
        self.displayed_folders = [f for f in self.displayed_folders if f.id != folder_id]
        InfoBar.success("已删除", "文件夹索引已删除", parent=self)
        self.update_stats()
        self.render_list()
    
    def _update_folder_status(self, folder_id: int, new_status: FolderStatus):
        """更新文件夹状态并重新渲染（不重新加载数据）"""
        # 更新 all_folders 中的状态（创建新对象替换旧的，因为 dataclass 是 frozen）
        new_all_folders = []
        for f in self.all_folders:
            if f.id == folder_id:
                # 创建新的对象，只修改 status
                new_f = SharedDriveFolder(
                    id=f.id,
                    project_id=f.project_id,
                    root_path=f.root_path,
                    folder_path=f.folder_path,
                    folder_name=f.folder_name,
                    file_count=f.file_count,
                    total_size=f.total_size,
                    modified_time=f.modified_time,
                    status=new_status,
                    match_score=f.match_score,
                    created_at=f.created_at,
                )
                new_all_folders.append(new_f)
            else:
                new_all_folders.append(f)
        self.all_folders = new_all_folders
        
        # 重新应用筛选并渲染
        self.apply_filters()
    
    def reload(self):
        """重新加载数据"""
        self.load_data()
    
    def set_shared_drive_path(self, path: str):
        """设置共享盘路径"""
        self.shared_drive_path = path
