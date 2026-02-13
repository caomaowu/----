from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog, QLabel
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, PrimaryPushSettingCard,
    SettingCard, LineEdit, FluentIcon as FI, InfoBar, ExpandLayout,
    PushButton
)

from dcpm.infra.config.user_config import load_user_config, save_user_config, UserConfig
from dcpm.services.scanner_service import scan_and_link_resources, targeted_scan_and_link
from dcpm.services.shared_drive_service import SharedDriveService
from dcpm.domain.project import Project
from dcpm.ui.dialogs.path_manager_dialog import PathManagerDialog


class LineEditSettingCard(SettingCard):
    """带输入框的设置卡片"""
    
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setFixedWidth(300)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class PathListCard(SettingCard):
    """显示路径列表摘要的卡片"""
    
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.pathLabel = QLabel(self)
        self.pathLabel.setStyleSheet("color: #666; font-size: 12px;")
        
        self.manageButton = PushButton("管理路径", self)
        self.manageButton.setFixedWidth(100)
        self.manageButton.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.hBoxLayout.addWidget(self.pathLabel, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addWidget(self.manageButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def set_paths(self, paths: list[str]):
        if not paths:
            self.pathLabel.setText("未设置路径")
        else:
            self.pathLabel.setText(f"已设置 {len(paths)} 个路径")



class ScanThread(QThread):
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, library_root: Path, shared_paths: list[str], target_project: Project | None = None):
        super().__init__()
        self.library_root = library_root
        self.shared_paths = shared_paths
        self.target_project = target_project

    def run(self):
        try:
            if self.target_project:
                count = targeted_scan_and_link(self.library_root, self.shared_paths, self.target_project)
            else:
                count = scan_and_link_resources(self.library_root, self.shared_paths)
            self.finished.emit(count)
        except Exception as e:
            self.error.emit(str(e))


class SettingsInterface(ScrollArea):
    """设置界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        self.setObjectName("settingsInterface")
        self.setStyleSheet("background-color: transparent;")
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        
        self._scan_thread: ScanThread | None = None
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        self.scrollWidget.setObjectName("scrollWidget")
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)

        # --- 外部资源集成 ---
        self.resource_group = SettingCardGroup("外部资源集成", self.scrollWidget)
        
        # 共享盘路径
        self.shared_path_card = PathListCard(
            FI.FOLDER,
            "探伤报告根目录",
            "设置公司共享盘的 UNC 路径或映射盘符",
            self.resource_group
        )
        self.shared_path_card.manageButton.clicked.connect(self._manage_inspection_paths)
        
        # 扫描按钮
        self.scan_card = PrimaryPushSettingCard(
            "立即扫描",
            FI.SYNC,
            "扫描共享盘",
            "根据路径规则自动关联探伤报告",
            self.resource_group
        )
        self.scan_card.clicked.connect(self._start_scan)

        self.resource_group.addSettingCard(self.shared_path_card)
        self.resource_group.addSettingCard(self.scan_card)
        
        # 共享盘文件夹索引组
        self.file_index_group = SettingCardGroup("共享盘文件夹索引", self.scrollWidget)
        
        # 共享盘文件夹路径列表
        self.file_index_path_card = PathListCard(
            FI.FOLDER,
            "共享盘文件夹",
            "设置需要索引的共享盘文件夹路径",
            self.file_index_group
        )
        self.file_index_path_card.manageButton.clicked.connect(self._manage_index_paths)
        
        # 索引按钮
        self.file_index_scan_card = PrimaryPushSettingCard(
            "开始索引",
            FI.SEARCH,
            "索引共享盘文件夹",
            "扫描所有配置的文件夹并自动关联与项目相关的内容",
            self.file_index_group
        )
        self.file_index_scan_card.clicked.connect(self._start_file_index_scan)
        
        self.file_index_group.addSettingCard(self.file_index_path_card)
        self.file_index_group.addSettingCard(self.file_index_scan_card)
        
        self.expandLayout.addWidget(self.resource_group)
        self.expandLayout.addWidget(self.file_index_group)

    def _load_config(self):
        cfg = load_user_config()
        self.shared_path_card.set_paths(cfg.shared_drive_paths)
        
        # 加载索引路径
        self.file_index_path_card.set_paths(cfg.index_root_paths)

    def _manage_inspection_paths(self):
        """打开探伤报告根目录管理对话框"""
        cfg = load_user_config()
        dialog = PathManagerDialog(cfg.shared_drive_paths, self)
        if dialog.exec():
            new_paths = dialog.get_paths()
            # 保存配置
            new_cfg = UserConfig(
                library_root=cfg.library_root,
                shared_drive_paths=new_paths,
                index_root_paths=cfg.index_root_paths,
                preset_tags=cfg.preset_tags
            )
            save_user_config(new_cfg)
            # 更新界面
            self.shared_path_card.set_paths(new_paths)
            InfoBar.success(
                title="保存成功",
                content="探伤报告根目录已更新",
                parent=self,
                duration=2000
            )

    def _manage_index_paths(self):
        """打开路径管理对话框"""
        cfg = load_user_config()
        dialog = PathManagerDialog(cfg.index_root_paths, self)
        if dialog.exec():
            new_paths = dialog.get_paths()
            # 保存配置
            new_cfg = UserConfig(
                library_root=cfg.library_root,
                shared_drive_paths=cfg.shared_drive_paths,
                index_root_paths=new_paths,
                preset_tags=cfg.preset_tags
            )
            save_user_config(new_cfg)
            # 更新界面
            self.file_index_path_card.set_paths(new_paths)
            InfoBar.success(
                title="保存成功",
                content="共享盘文件夹路径已更新",
                parent=self,
                duration=2000
            )

    def _start_scan(self):
        cfg = load_user_config()
        if not cfg.library_root:
            InfoBar.warning(
                title="无法扫描",
                content="请先在主页选择项目库根目录",
                parent=self,
                duration=3000
            )
            return
            
        shared_paths = cfg.shared_drive_paths
        if not shared_paths:
            InfoBar.warning(
                title="无法扫描",
                content="请先设置探伤报告根目录",
                parent=self,
                duration=3000
            )
            return

        self.scan_card.button.setEnabled(False)
        self.scan_card.button.setText("扫描中...")
        
        self._scan_thread = ScanThread(Path(cfg.library_root), shared_paths)
        self._scan_thread.finished.connect(self._on_scan_finished)
        self._scan_thread.error.connect(self._on_scan_error)
        self._scan_thread.start()

    def _on_scan_finished(self, count: int):
        self.scan_card.button.setEnabled(True)
        self.scan_card.button.setText("立即扫描")
        InfoBar.success(
            title="扫描完成",
            content=f"已成功关联 {count} 个新的探伤资源",
            parent=self,
            duration=3000
        )

    def _on_scan_error(self, err: str):
        self.scan_card.button.setEnabled(True)
        self.scan_card.button.setText("立即扫描")
        InfoBar.error(
            title="扫描失败",
            content=err,
            parent=self,
            duration=5000
        )
    
    def _start_file_index_scan(self):
        """开始共享盘文件夹索引扫描"""
        cfg = load_user_config()
        if not cfg.library_root:
            InfoBar.warning(
                title="无法扫描",
                content="请先在主页选择项目库根目录",
                parent=self,
                duration=3000
            )
            return
        
        root_paths = cfg.index_root_paths
        if not root_paths:
            InfoBar.warning(
                title="无法扫描",
                content="请先设置共享盘文件夹路径",
                parent=self,
                duration=3000
            )
            return
        
        self.file_index_scan_card.button.setEnabled(False)
        self.file_index_scan_card.button.setText("索引中...")
        
        # 使用线程执行扫描
        from PyQt6.QtCore import QThread, pyqtSignal
        
        class FileIndexThread(QThread):
            finished = pyqtSignal(int)
            error = pyqtSignal(str)
            
            def __init__(self, library_root: Path, shared_paths: list[str]):
                super().__init__()
                self.library_root = library_root
                self.shared_paths = shared_paths
            
            def run(self):
                try:
                    service = SharedDriveService(self.library_root)
                    count = service.scan_and_index(self.shared_paths)
                    self.finished.emit(count)
                except Exception as e:
                    self.error.emit(str(e))
        
        self._file_index_thread = FileIndexThread(Path(cfg.library_root), root_paths)
        self._file_index_thread.finished.connect(self._on_file_index_finished)
        self._file_index_thread.error.connect(self._on_file_index_error)
        self._file_index_thread.start()
    
    def _on_file_index_finished(self, count: int):
        self.file_index_scan_card.button.setEnabled(True)
        self.file_index_scan_card.button.setText("开始索引")
        InfoBar.success(
            title="索引完成",
            content=f"已成功索引 {count} 个文件夹",
            parent=self,
            duration=3000
        )
    
    def _on_file_index_error(self, err: str):
        self.file_index_scan_card.button.setEnabled(True)
        self.file_index_scan_card.button.setText("开始索引")
        InfoBar.error(
            title="索引失败",
            content=err,
            parent=self,
            duration=5000
        )
