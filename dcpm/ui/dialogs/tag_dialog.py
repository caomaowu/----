from qfluentwidgets import MessageBoxBase, SubtitleLabel, PlainTextEdit

class TagDialog(MessageBoxBase):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.textEdit = PlainTextEdit(self)
        self.textEdit.setPlainText(content)
        self.textEdit.setPlaceholderText("用逗号分隔标签，例如：第一版, 第二版, 常用")
        self.textEdit.setMinimumHeight(120)
        self.textEdit.setMinimumWidth(320)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textEdit)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")

        self.widget.setMinimumWidth(360)

    def get_text(self) -> str:
        return self.textEdit.toPlainText()
