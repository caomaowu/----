from datetime import datetime
from qfluentwidgets import (
    SubtitleLabel, StrongBodyLabel, LineEdit, MessageBoxBase, CheckBox
)
from dcpm.services.project_service import CreateProjectRequest

class CreateProjectDialog(MessageBoxBase):
    """Fluent 风格的新建项目对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("新建项目", self)
        
        # 字段容器
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        # 月份
        self.monthLabel = StrongBodyLabel("月份 (YYYY-MM)", self)
        self.monthEdit = LineEdit(self)
        self.monthEdit.setText(datetime.now().strftime("%Y-%m"))
        self.monthEdit.setPlaceholderText("例如: 2024-03")
        self.viewLayout.addWidget(self.monthLabel)
        self.viewLayout.addWidget(self.monthEdit)
        self.viewLayout.addSpacing(12)
        
        # 客户
        self.custLabel = StrongBodyLabel("客户名称", self)
        self.custEdit = LineEdit(self)
        self.custEdit.setPlaceholderText("例如: BMW, Tesla")
        self.viewLayout.addWidget(self.custLabel)
        self.viewLayout.addWidget(self.custEdit)
        self.viewLayout.addSpacing(12)

        # 料号
        self.pnLabel = StrongBodyLabel("料号 (可选)", self)
        self.pnEdit = LineEdit(self)
        self.pnEdit.setPlaceholderText("例如: 17045324")
        self.viewLayout.addWidget(self.pnLabel)
        self.viewLayout.addWidget(self.pnEdit)
        self.viewLayout.addSpacing(12)
        
        # 项目名称
        self.nameLabel = StrongBodyLabel("项目名称", self)
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("输入项目名称")
        self.viewLayout.addWidget(self.nameLabel)
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addSpacing(12)
        
        # 标签
        self.tagsLabel = StrongBodyLabel("标签 (可选)", self)
        self.tagsEdit = LineEdit(self)
        self.tagsEdit.setPlaceholderText("用逗号分隔，如: 压铸, 模具")
        self.viewLayout.addWidget(self.tagsLabel)
        self.viewLayout.addWidget(self.tagsEdit)
        self.viewLayout.addSpacing(16)
        
        # 特殊项目选项
        self.specialCheckBox = CheckBox("特殊项目（不参与探伤和共享盘索引）", self)
        self.viewLayout.addWidget(self.specialCheckBox)
        
        # 调整按钮文字
        self.yesButton.setText("创建项目")
        self.cancelButton.setText("取消")
        
        # 简单的验证逻辑
        self.widget.setMinimumWidth(360)
        self.yesButton.setDisabled(True)
        self.custEdit.textChanged.connect(self._validate)
        self.nameEdit.textChanged.connect(self._validate)
        self.monthEdit.textChanged.connect(self._validate)

    def _validate(self):
        valid = bool(self.custEdit.text().strip() and 
                     self.nameEdit.text().strip() and 
                     self.monthEdit.text().strip())
        self.yesButton.setDisabled(not valid)

    def build_request(self):
        return CreateProjectRequest(
            month=self.monthEdit.text(),
            customer=self.custEdit.text(),
            name=self.nameEdit.text(),
            tags=self.tagsEdit.text().split(","),
            part_number=self.pnEdit.text(),
            is_special=self.specialCheckBox.isChecked()
        )
