from PyQt6.QtCore import Qt, QSize, QModelIndex, QRect
from PyQt6.QtGui import QPainter, QColor, QIcon
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from dcpm.ui.theme.colors import COLORS

class FileItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, tag_provider=None):
        super().__init__(parent)
        self.margins = 8
        self.icon_size = 48
        self.tag_provider = tag_provider
        
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(100, 130)  # Width, Height for grid items

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw background for selection/hover
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setBrush(QColor(COLORS['primary_light']))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(option.rect.adjusted(4, 4, -4, -4), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QColor(COLORS['bg'])) # Slightly darker than app bg
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(option.rect.adjusted(4, 4, -4, -4), 8, 8)

        # Draw Icon
        # We get the icon from the model (QFileSystemModel provides system icons)
        icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
        name: str = index.data(Qt.ItemDataRole.DisplayRole)
        
        rect = option.rect
        icon_rect = rect.adjusted(0, 12, 0, -40) # Top area for icon
        
        if icon:
            pixmap = icon.pixmap(self.icon_size, self.icon_size)
            # Center icon
            x = icon_rect.x() + (icon_rect.width() - self.icon_size) // 2
            y = icon_rect.y() + (icon_rect.height() - self.icon_size) // 2
            painter.drawPixmap(x, y, pixmap)

        # Draw Text
        text_rect = rect.adjusted(4, self.icon_size + 20, -4, -4)
        painter.setPen(QColor(COLORS['text']))
        
        # Elide text if too long
        fm = option.fontMetrics
        elided_text = fm.elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width())
        
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided_text)

        tags: list[str] = []
        if callable(self.tag_provider):
            try:
                tags = list(self.tag_provider(index) or [])
            except Exception:
                tags = []

        if tags:
            tags = tags[:2]
            more_count = 0
            if callable(self.tag_provider):
                try:
                    all_tags = list(self.tag_provider(index) or [])
                    more_count = max(0, len(all_tags) - len(tags))
                except Exception:
                    more_count = 0
            if more_count > 0:
                tags = tags + [f"+{more_count}"]

            tag_font = option.font
            if tag_font.pointSize() > 9:
                tag_font.setPointSize(tag_font.pointSize() - 2)
            painter.setFont(tag_font)
            fm2 = painter.fontMetrics()

            pad_x = 6
            pad_y = 2
            gap = 6
            chip_h = fm2.height() + pad_y * 2
            y = text_rect.y() + fm.height() + 6

            widths = [fm2.horizontalAdvance(t) + pad_x * 2 for t in tags]
            total_w = sum(widths) + gap * (len(widths) - 1)
            x = rect.x() + max(0, (rect.width() - total_w) // 2)

            bg = QColor(COLORS["primary"])
            bg.setAlpha(26)
            border = QColor(COLORS["primary"])
            border.setAlpha(64)

            for t, w in zip(tags, widths):
                chip_rect = QRect(x, y, w, chip_h)
                painter.setBrush(bg)
                painter.setPen(border)
                painter.drawRoundedRect(chip_rect, 8, 8)
                painter.setPen(QColor(COLORS["primary"]))
                painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, t)
                x += w + gap
        
        painter.restore()
