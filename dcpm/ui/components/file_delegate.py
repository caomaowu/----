from PyQt6.QtCore import Qt, QSize, QModelIndex, QRect
from PyQt6.QtGui import QPainter, QColor, QIcon, QPixmap, QFileSystemModel
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from dcpm.ui.theme.colors import COLORS, get_tag_colors

class FileItemDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, tag_provider=None, thumbnail_provider=None):
        super().__init__(parent)
        self.margins = 8
        self.icon_size = 48
        self.tag_provider = tag_provider
        self.thumbnail_provider = thumbnail_provider
        self.view_mode = "icon" # "icon" or "list"

    def set_view_mode(self, mode: str):
        self.view_mode = mode

    def _get_tags(self, index):
        if callable(self.tag_provider):
            try:
                return list(self.tag_provider(index) or [])
            except Exception:
                return []
        return []

    def _calculate_tag_layout(self, tags, fm, max_width, start_x=0, start_y=0):
        """
        Calculate positions for tags with wrapping.
        Returns: (total_height, list of (rect, tag_text))
        """
        if not tags:
            return 0, []
        
        pad_x = 6
        pad_y = 2
        gap_x = 6
        gap_y = 4
        chip_h = fm.height() + pad_y * 2
        
        positions = []
        current_x = start_x
        current_y = start_y
        
        # Ensure max_width is reasonable
        if max_width < 50: 
            max_width = 50

        for t in tags:
            w = fm.horizontalAdvance(t) + pad_x * 2
            
            # Wrap if not the first item and exceeds width
            if current_x + w > start_x + max_width and current_x > start_x:
                current_x = start_x
                current_y += chip_h + gap_y
            
            positions.append((QRect(current_x, current_y, w, chip_h), t))
            current_x += w + gap_x
            
        total_height = (current_y - start_y) + chip_h
        return total_height, positions

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        tags = self._get_tags(index)
        
        # Use a default font if option.font is not fully ready (though usually it is)
        fm = option.fontMetrics
        # For tags we usually use a slightly smaller font
        # We can approximate or clone font. 
        # But to be fast, let's just use current font metrics or adjust slightly.
        # In paint we use pointSize - 2 for tags.
        
        if self.view_mode == "list":
            width = option.rect.width()
            if width <= 0: width = 500 # Fallback
            
            # Base height for icon/text line
            base_height = 36
            
            if not tags:
                return QSize(width, base_height)
            
            # Calculate tag height
            # Tags start below text? Or right?
            # User wants "Show All".
            # Strategy: 
            # Row 1: Icon + Name
            # Row 2+: Tags
            
            # Available width for tags
            # Indent tags to align with text? Text starts at: padding(8) + icon(24) + gap(12) = 44
            tag_start_x = 44
            avail_w = width - tag_start_x - 20 # Right padding
            
            # Use smaller font for metric calculation
            # Note: We can't easily change FM here without a painter or font copy, 
            # but we can assume tag font is smaller.
            # Let's just use the standard FM but maybe scale down width slightly if needed, 
            # or just use it as is (safer to overestimate height).
            
            tag_h, _ = self._calculate_tag_layout(tags, fm, avail_w, 0, 0)
            
            return QSize(width, base_height + tag_h + 4) # 4px bottom padding

        else: # Grid Mode
            width = 100 # Fixed width for grid item
            base_height = 130 # 12 + icon(48) + 8 + text(height) + 6 + ...
            
            if not tags:
                return QSize(width, base_height)
            
            # For Grid, tags are at the bottom.
            # We need to calculate how much extra height they need.
            # Default base_height included maybe 1 row of tags or so.
            # Let's recalculate from scratch or add delta.
            
            # Icon (12 top + 48 size + 8 gap) = 68
            # Text (approx 2 lines allowed? say 36px) = 104
            # Gap 6 = 110
            
            current_y = 110
            tag_h, _ = self._calculate_tag_layout(tags, fm, width - 8, 0, 0) # 4px padding each side
            
            return QSize(width, current_y + tag_h + 12)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        tags = self._get_tags(index)

        # Draw background for selection/hover
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = QColor(COLORS['primary_light'])
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            # Adjust rect for background to look like a card/row
            if self.view_mode == "list":
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
            else:
                painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            bg_color = QColor(COLORS['bg'])
            painter.setBrush(bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            if self.view_mode == "list":
                painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)
            else:
                painter.drawRoundedRect(rect.adjusted(4, 4, -4, -4), 8, 8)

        # 获取数据
        file_path = ""
        model = index.model()
        if isinstance(model, QFileSystemModel):
            file_path = model.filePath(index)

        # Prepare Tag Font
        tag_font = option.font
        if tag_font.pointSize() > 9:
            tag_font.setPointSize(tag_font.pointSize() - 2)
        
        # --- 列表模式渲染 ---
        if self.view_mode == "list":
            icon_size = 24
            padding = 8
            
            # 1. 图标 (Top-Left aligned within the row)
            # Row 1 height is approx 36. Center icon in that top strip.
            top_row_h = 36
            icon_rect = QRect(rect.x() + padding, rect.y() + (top_row_h - icon_size)//2, icon_size, icon_size)
            
            # Draw Icon/Thumbnail
            self._draw_icon(painter, index, file_path, icon_rect, icon_size)
            
            # 2. 文件名
            name = index.data(Qt.ItemDataRole.DisplayRole)
            text_x = icon_rect.right() + 12
            text_width = rect.width() - text_x - padding
            text_rect = QRect(text_x, rect.y(), text_width, top_row_h)
            
            painter.setPen(QColor(COLORS['text']))
            # Align Left VCenter
            elided_text = option.fontMetrics.elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_text)
            
            # 3. 标签 (New Line)
            if tags:
                tag_start_x = text_x # Align with text
                tag_start_y = rect.y() + top_row_h - 4 # Start slightly overlapping the bottom padding of row 1
                avail_w = rect.width() - tag_start_x - 20
                
                painter.setFont(tag_font)
                fm_tag = painter.fontMetrics()
                
                _, positions = self._calculate_tag_layout(tags, fm_tag, avail_w, tag_start_x, tag_start_y)
                
                self._draw_tags(painter, positions)

            painter.restore()
            return

        # --- 图标模式渲染 ---
        
        # 1. 图标区域
        icon_top_margin = 12
        icon_x = rect.x() + (rect.width() - self.icon_size) // 2
        icon_y = rect.y() + icon_top_margin
        
        # Draw Icon
        icon_rect = QRect(icon_x, icon_y, self.icon_size, self.icon_size)
        self._draw_icon(painter, index, file_path, icon_rect, self.icon_size)

        # 2. 文本区域
        text_top_gap = 8
        text_y = icon_y + self.icon_size + text_top_gap
        fm = option.fontMetrics
        text_height = fm.height()
        text_rect = QRect(rect.x() + 4, text_y, rect.width() - 8, text_height)
        
        name: str = index.data(Qt.ItemDataRole.DisplayRole)
        painter.setPen(QColor(COLORS['text']))
        elided_text = fm.elidedText(name, Qt.TextElideMode.ElideMiddle, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, elided_text)

        # 3. 标签区域
        if tags:
            tag_top_gap = 6
            tag_y = text_y + text_height + tag_top_gap
            
            painter.setFont(tag_font)
            fm_tag = painter.fontMetrics()
            
            # Grid mode tags: centered? or left?
            # _calculate_tag_layout uses left alignment relative to start_x.
            # To center, we might need to calculate row by row width.
            # For simplicity, let's just left align within the item rect (with padding).
            
            tag_start_x = rect.x() + 4
            tag_avail_w = rect.width() - 8
            
            _, positions = self._calculate_tag_layout(tags, fm_tag, tag_avail_w, tag_start_x, tag_y)
            self._draw_tags(painter, positions)
        
        painter.restore()

    def _draw_icon(self, painter, index, file_path, rect, size):
        icon_drawn = False
        if self.thumbnail_provider and file_path:
             thumb = self.thumbnail_provider.get_thumbnail(file_path)
             if thumb:
                 scaled = thumb.scaled(
                     size, size,
                     Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation
                 )
                 tx = rect.x() + (size - scaled.width()) // 2
                 ty = rect.y() + (size - scaled.height()) // 2
                 painter.drawPixmap(tx, ty, scaled)
                 icon_drawn = True

        if not icon_drawn:
            icon = index.data(Qt.ItemDataRole.DecorationRole)
            if icon:
                pixmap = icon.pixmap(size, size)
                painter.drawPixmap(rect.x(), rect.y(), pixmap)

    def _draw_tags(self, painter, positions):
        for rect, t in positions:
            bg_hex, text_hex = get_tag_colors(t)
            
            painter.setBrush(QColor(bg_hex))
            border_color = QColor(text_hex)
            border_color.setAlpha(80) 
            painter.setPen(border_color)
            
            painter.drawRoundedRect(rect, 4, 4)
            
            painter.setPen(QColor(text_hex))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, t)
