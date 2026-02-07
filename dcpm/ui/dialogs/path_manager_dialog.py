from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QFileDialog, QLabel
)
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, PrimaryPushButton, 
    PushButton, FluentIcon as FI, themeColor
)

class PathManagerDialog(MessageBoxBase):
    """共享盘路径管理对话框"""
    
    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("管理共享盘文件夹路径", self)
        
        # 路径列表
        self.listWidget = QListWidget(self)
        self.listWidget.setAlternatingRowColors(True)
        self.listWidget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.listWidget.setMinimumHeight(200)
        self.listWidget.setMinimumWidth(400)
        
        # 初始化列表
        for path in paths:
            self._add_path_item(path)
            
        # 按钮栏
        self.buttonLayout = QHBoxLayout()
        
        self.addButton = PrimaryPushButton(FI.ADD, "添加文件夹", self)
        self.removeButton = PushButton(FI.DELETE, "删除选中", self)
        self.removeButton.setEnabled(False)
        
        self.buttonLayout.addWidget(self.addButton)
        self.buttonLayout.addWidget(self.removeButton)
        self.buttonLayout.addStretch(1)
        
        # 布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addLayout(self.buttonLayout)
        self.viewLayout.addWidget(self.listWidget)
        
        # 信号连接
        self.addButton.clicked.connect(self._add_folder)
        self.removeButton.clicked.connect(self._remove_selected)
        self.listWidget.itemSelectionChanged.connect(self._update_button_state)
        
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(500)

    def _add_path_item(self, path: str):
        item = QListWidgetItem(path)
        item.setToolTip(path)
        self.listWidget.addItem(item)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, 
            "选择共享盘文件夹",
            ""
        )
        
        if folder:
            # 检查是否重复
            existing = [self.listWidget.item(i).text() for i in range(self.listWidget.count())]
            if folder not in existing:
                self._add_path_item(folder)

    def _remove_selected(self):
        row = self.listWidget.currentRow()
        if row >= 0:
            self.listWidget.takeItem(row)

    def _update_button_state(self):
        self.removeButton.setEnabled(self.listWidget.count() > 0 and self.listWidget.currentRow() >= 0)

    def get_paths(self) -> list[str]:
        return [self.listWidget.item(i).text() for i in range(self.listWidget.count())]
