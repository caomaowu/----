from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from qfluentwidgets import (
    ScrollArea, SettingCardGroup, PrimaryPushSettingCard,
    SettingCard, LineEdit, FluentIcon as FI, InfoBar, ExpandLayout
)

from dcpm.infra.config.user_config import load_user_config, save_user_config, UserConfig
from dcpm.services.scanner_service import scan_and_link_resources, targeted_scan_and_link
from dcpm.services.shared_drive_service import SharedDriveService
from dcpm.domain.project import Project


class LineEditSettingCard(SettingCard):
    """带输入框的设置卡片"""
    
    def __init__(self, icon, title, content=None, parent=None):
        super().__init__(icon, title, content, parent)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setFixedWidth(300)
        self.hBoxLayout.addWidget(self.lineEdit, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)


class ScanThread(QThread):
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, library_root: Path, shared_path: str, target_project: Project | None = None):
        super().__init__()
        self.library_root = library_root
        self.shared_path = shared_path
        self.target_project = target_project

    def run(self):
        try:
            if self.target_project:
                count = targeted_scan_and_link(self.library_root, self.shared_path, self.target_project)
            else:
                count = scan_and_link_resources(self.library_root, self.shared_path)
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
        self.shared_path_card = LineEditSettingCard(
            FI.FOLDER,
            "探伤报告根目录",
            "设置公司共享盘的 UNC 路径或映射盘符",
            self.resource_group
        )
        self.shared_path_card.lineEdit.setPlaceholderText(r"例如: \\192.168.1.100\QualityControl\Inspection")
        # 当文本改变时保存配置（简单起见，失去焦点或手动保存更好，这里简单实现为手动保存或实时）
        # LineEditSettingCard doesn't have textChanged signal exposed directly easily, usually use lineEdit.textChanged
        self.shared_path_card.lineEdit.editingFinished.connect(self._save_path)
        
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
        
        # 共享盘文件索引组
        self.file_index_group = SettingCardGroup("共享盘文件索引", self.scrollWidget)
        
        # 共享盘文件路径（可复用探伤报告路径或单独设置）
        self.file_index_path_card = LineEditSettingCard(
            FI.FOLDER,
            "共享盘根目录",
            "设置共享盘的根目录路径，用于索引项目相关文件",
            self.file_index_group
        )
        self.file_index_path_card.lineEdit.setPlaceholderText(r"例如: \\192.168.1.100\Engineering")
        self.file_index_path_card.lineEdit.editingFinished.connect(self._save_file_index_path)
        
        # 索引按钮
        self.file_index_scan_card = PrimaryPushSettingCard(
            "开始索引",
            FI.SEARCH,
            "索引共享盘文件",
            "扫描共享盘并自动关联与项目相关的文件",
            self.file_index_group
        )
        self.file_index_scan_card.clicked.connect(self._start_file_index_scan)
        
        self.file_index_group.addSettingCard(self.file_index_path_card)
        self.file_index_group.addSettingCard(self.file_index_scan_card)
        
        self.expandLayout.addWidget(self.resource_group)
        self.expandLayout.addWidget(self.file_index_group)

    def _load_config(self):
        cfg = load_user_config()
        if cfg.shared_drive_path:
            self.shared_path_card.lineEdit.setText(cfg.shared_drive_path)
            # 默认复用探伤报告路径
            self.file_index_path_card.lineEdit.setText(cfg.shared_drive_path)

    def _save_path(self):
        path = self.shared_path_card.lineEdit.text().strip()
        cfg = load_user_config()
        new_cfg = UserConfig(
            library_root=cfg.library_root,
            shared_drive_path=path,
            preset_tags=cfg.preset_tags
        )
        save_user_config(new_cfg)
    
    def _save_file_index_path(self):
        path = self.file_index_path_card.lineEdit.text().strip()
        cfg = load_user_config()
        # 这里我们复用 shared_drive_path 字段，或者可以添加新的字段
        new_cfg = UserConfig(
            library_root=cfg.library_root,
            shared_drive_path=path,
            preset_tags=cfg.preset_tags
        )
        save_user_config(new_cfg)

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
            
        shared_path = self.shared_path_card.lineEdit.text().strip()
        if not shared_path:
            InfoBar.warning(
                title="无法扫描",
                content="请先设置共享盘路径",
                parent=self,
                duration=3000
            )
            return

        self.scan_card.button.setEnabled(False)
        self.scan_card.button.setText("扫描中...")
        
        self._scan_thread = ScanThread(Path(cfg.library_root), shared_path)
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
        """开始共享盘文件索引扫描"""
        cfg = load_user_config()
        if not cfg.library_root:
            InfoBar.warning(
                title="无法扫描",
                content="请先在主页选择项目库根目录",
                parent=self,
                duration=3000
            )
            return
        
        shared_path = self.file_index_path_card.lineEdit.text().strip()
        if not shared_path:
            InfoBar.warning(
                title="无法扫描",
                content="请先设置共享盘根目录路径",
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
            
            def __init__(self, library_root: Path, shared_path: str):
                super().__init__()
                self.library_root = library_root
                self.shared_path = shared_path
            
            def run(self):
                try:
                    service = SharedDriveService(self.library_root)
                    count = service.scan_and_index(self.shared_path)
                    self.finished.emit(count)
                except Exception as e:
                    self.error.emit(str(e))
        
        self._file_index_thread = FileIndexThread(Path(cfg.library_root), shared_path)
        self._file_index_thread.finished.connect(self._on_file_index_finished)
        self._file_index_thread.error.connect(self._on_file_index_error)
        self._file_index_thread.start()
    
    def _on_file_index_finished(self, count: int):
        self.file_index_scan_card.button.setEnabled(True)
        self.file_index_scan_card.button.setText("开始索引")
        InfoBar.success(
            title="索引完成",
            content=f"已成功索引 {count} 个文件",
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
