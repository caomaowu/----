from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QModelIndex, QPoint, QDir, QUrl, QMimeData, QRect
from PyQt6.QtGui import QDesktopServices, QAction, QCursor, QColor, QPainter, QFileSystemModel, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QStyle, 
    QStyledItemDelegate, QMenu, QApplication, QFrame, QLabel, QStyleOptionViewItem, QInputDialog, QMessageBox,
    QStackedWidget
)
from qfluentwidgets import (
    BreadcrumbBar, FluentIcon, TransparentToolButton, 
    SearchLineEdit, Action, CommandBar, Flyout, FlyoutAnimationType, MessageBoxBase, SubtitleLabel, BodyLabel, InfoBar, InfoBarPosition, PlainTextEdit,
    Pivot
)

from dcpm.ui.theme.colors import COLORS
from dcpm.services.note_service import NoteService
from dcpm.services.tag_service import TagService
from dcpm.ui.components.note_dialog import NoteDialog
from dcpm.ui.views.inspection_timeline import InspectionTimeline

class FileIconProvider(QFileSystemModel):
    """Custom FileSystemModel to provide better icons if needed, 
    but for now standard QFileSystemModel is okay. 
    We can override data() to return FluentIcons for folders if we want."""
    pass


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


class FileBrowser(QWidget):
    backRequested = pyqtSignal()

    def __init__(self, library_root: Path, parent=None):
        super().__init__(parent)
        self.library_root = library_root
        self.note_service = NoteService(library_root)
        self.tag_service = TagService(library_root)
        self.setAcceptDrops(True) # Enable Drag & Drop
        self.current_root: Path | None = None
        self.project_root: Path | None = None
        self.project_id: str = ""
        self._item_tags: dict[str, list[str]] = {}
        
        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(32, 20, 32, 20)
        self._layout.setSpacing(16)

        # Header
        self._init_header()
        
        # Pivot (Tabs)
        self.pivot = Pivot(self)
        self.pivot.addItem("files", "项目文件")
        self.pivot.addItem("inspection", "探伤记录")
        self.pivot.currentItemChanged.connect(self._on_pivot_changed)
        self._layout.addWidget(self.pivot)
        
        # Stacked Content
        self.stack = QStackedWidget(self)
        self._layout.addWidget(self.stack)
        
        # Page 0: File View
        self.file_view_container = QWidget()
        self.file_view_layout = QVBoxLayout(self.file_view_container)
        self.file_view_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.file_view_container)
        
        self._init_file_view()
        
        # Page 1: Timeline (Placeholder)
        self.timeline_view = QWidget()
        self.stack.addWidget(self.timeline_view)

    def _on_pivot_changed(self, key: str):
        if key == "files":
            self.stack.setCurrentIndex(0)
        elif key == "inspection":
            self.stack.setCurrentIndex(1)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not self.current_root:
            return
            
        # Determine Drop Target
        target_dir = None
        
        # Check if dropped onto a specific item (folder) in the list view
        # We need to map the position to the list view coordinate system if needed, 
        # but since dropEvent is on FileBrowser (parent), we need to check if cursor is over a list item.
        # Actually, since we disabled drop on ListView, the event bubbles to FileBrowser with global pos?
        # No, it's relative to FileBrowser.
        
        # Let's try to find the index under mouse position
        # We need to map pos to list_view coordinates
        list_view_pos = self.list_view.mapFrom(self, event.position().toPoint())
        index = self.list_view.indexAt(list_view_pos)
        
        if index.isValid():
            info = self.model.fileInfo(index)
            if info.isDir():
                target_dir = Path(self.model.filePath(index))
        
        # If not dropped on a folder, use current directory
        if not target_dir:
            current_idx = self.list_view.rootIndex()
            target_dir = Path(self.model.filePath(current_idx))
            
            if not target_dir.exists():
                target_dir = self.current_root

        urls = event.mimeData().urls()
        imported_count = 0
        for url in urls:
            src_path = Path(url.toLocalFile())
            if src_path.exists():
                # Prevent self-copy (Source == Destination)
                if src_path.parent == target_dir:
                    continue
                    
                try:
                    dest_path = target_dir / src_path.name
                    if dest_path.exists():
                        # Simple collision handling: skip or could show dialog
                        # For now, let's append timestamp if exists
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%H%M%S")
                        dest_path = target_dir / f"{src_path.stem}_{timestamp}{src_path.suffix}"
                    
                    if src_path.is_dir():
                        shutil.copytree(src_path, dest_path)
                    else:
                        shutil.copy2(src_path, dest_path)
                    imported_count += 1
                except Exception as e:
                    # In a real app, show error dialog
                    print(f"Error copying file: {e}")
        
        if imported_count > 0:
            InfoBar.success(
                title='导入成功',
                content=f"已成功导入 {imported_count} 个文件",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2000,
                parent=self
            )

        event.accept()

    def _init_header(self):
        header = QHBoxLayout()
        header.setSpacing(12)

        # Back Button
        self.back_btn = TransparentToolButton(FluentIcon.LEFT_ARROW, self)
        self.back_btn.setFixedSize(32, 32)
        self.back_btn.clicked.connect(self._on_back_clicked)
        header.addWidget(self.back_btn)

        # Breadcrumb
        self.breadcrumb = BreadcrumbBar()
        self.breadcrumb.setSpacing(8)
        self.breadcrumb.currentItemChanged.connect(self._on_breadcrumb_clicked)
        header.addWidget(self.breadcrumb)
        
        header.addStretch(1)

        # Actions
        self.open_explorer_btn = TransparentToolButton(FluentIcon.FOLDER, self)
        self.open_explorer_btn.setToolTip("在资源管理器中打开")
        self.open_explorer_btn.clicked.connect(self._open_in_explorer)
        header.addWidget(self.open_explorer_btn)
        
        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.clicked.connect(self._refresh)
        header.addWidget(self.refresh_btn)

        self._layout.addLayout(header)

    def _init_file_view(self):
        self.model = QFileSystemModel()
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)
        self.model.setNameFilters(["*"])
        self.model.setNameFilterDisables(False)
        
        # Use a nicer icon provider if we had one, but default is okay for now
        # self.model.setIconProvider(...)

        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setWordWrap(True)
        self.list_view.setSpacing(8)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setFrameShape(QFrame.Shape.NoFrame)
        self.list_view.setStyleSheet("background: transparent; border: none;")
        self.list_view.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        
        # Drag & Drop Configuration
        self.list_view.setAcceptDrops(False) # Disable default view drop to let parent handle it, or we handle it here
        # Actually, QListView consumes drop events if setAcceptDrops is True. 
        # But we implemented dragEnterEvent/dropEvent on the parent Widget (FileBrowser).
        # QListView is a child of FileBrowser. If mouse is over QListView, it receives the event first.
        # If it doesn't accept drops, the event propagates to parent.
        # BUT, standard QListView might not propagate nicely if it thinks it can handle something or just ignores.
        # Let's ensure QListView ignores drops so parent gets them, OR we install event filter.
        # The safest way for "blank area drop" is letting the parent handle it.
        # Let's explicitly ignore drops on list view to bubble up.
        self.list_view.setAcceptDrops(False) 
        self.list_view.setDragEnabled(True) # Allow dragging items OUT (or within)
        self.list_view.setDragDropMode(QListView.DragDropMode.DragOnly) # We handle drops manually on parent
        
        # Custom Delegate for Fluent Look
        self.delegate = FileItemDelegate(self.list_view, self._get_tags_for_index)
        self.list_view.setItemDelegate(self.delegate)
        
        # Signals
        self.list_view.doubleClicked.connect(self._on_item_double_clicked)
        self.list_view.clicked.connect(self._on_item_clicked)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)

        self.file_view_layout.addWidget(self.list_view)

    def set_root(self, path: Path, project_name: str = "", project_id: str = ""):
        """Entry point: Navigate to a project folder"""
        if not path.exists():
            return
            
        self.current_root = path
        self.project_root = path
        self.project_name = project_name
        self.project_id = project_id
        
        # Reset Pivot
        self.pivot.setCurrentItem("files")
        
        # Re-init timeline
        if self.project_id:
            old_widget = self.timeline_view
            self.stack.removeWidget(old_widget)
            old_widget.deleteLater()
            
            self.timeline_view = InspectionTimeline(self.library_root, self.project_id, self)
            self.stack.addWidget(self.timeline_view)

        try:
            self._item_tags = self.tag_service.load_item_tags(path)
        except Exception:
            self._item_tags = {}
        
        # Set model root path (needs to be set to load data)
        root_idx = self.model.setRootPath(str(path))
        self.list_view.setRootIndex(root_idx)
        
        self._update_breadcrumbs(path)
        self.list_view.viewport().update()

    def _rel_path_for_fs_path(self, fs_path: str) -> str:
        if not self.project_root:
            return ""
        try:
            rel = Path(fs_path).resolve().relative_to(self.project_root.resolve()).as_posix()
        except Exception:
            return ""
        rel = rel.strip().replace("\\", "/")
        if rel == ".":
            return ""
        return rel.strip("/")

    def _get_tags_for_index(self, index: QModelIndex) -> list[str]:
        if not index.isValid():
            return []
        p = self.model.filePath(index)
        rel = self._rel_path_for_fs_path(p)
        if not rel:
            return []
        return self._item_tags.get(rel, [])

    def _edit_tags(self, fs_path: str):
        if not self.project_root:
            return
        rel = self._rel_path_for_fs_path(fs_path)
        if not rel:
            return
        current = self._item_tags.get(rel, [])
        w = TagDialog("设置标签", ", ".join(current), self.window())
        if w.exec():
            tags = self.tag_service.parse_tags_text(w.get_text())
            try:
                self._item_tags = self.tag_service.set_item_tags(self.project_root, rel, tags)
                self.list_view.viewport().update()
                InfoBar.success(
                    title="已保存",
                    content="标签已更新",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000,
                    parent=self,
                )
            except Exception as e:
                InfoBar.error(
                    title="保存失败",
                    content=str(e),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000,
                    parent=self,
                )

    def _update_breadcrumbs(self, current_path: Path):
        """Rebuild breadcrumbs based on relative path from project root"""
        self.breadcrumb.clear()
        
        # Add "Project Root" item
        self.breadcrumb.addItem(self.project_name or self.current_root.name, str(self.current_root))
        
        if current_path == self.current_root:
            self.breadcrumb.setCurrentItem(str(self.current_root))
            return
            
        try:
            rel = current_path.relative_to(self.current_root)
            parts = rel.parts
            accumulated = self.current_root
            for part in parts:
                accumulated = accumulated / part
                self.breadcrumb.addItem(part, str(accumulated))
            
            self.breadcrumb.setCurrentItem(str(current_path))
        except ValueError:
            # Should not happen if we only navigate inside
            pass

    def _on_breadcrumb_clicked(self, path_str: str):
        path = Path(path_str)
        if path.exists():
            self.list_view.setRootIndex(self.model.index(str(path)))

    def _on_item_double_clicked(self, index: QModelIndex):
        file_path = self.model.filePath(index)
        info = self.model.fileInfo(index)
        
        if info.isDir():
            # Navigate into directory
            self.list_view.setRootIndex(index)
            self._update_breadcrumbs(Path(file_path))
        else:
            # Open file
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def _on_back_clicked(self):
        # Check if we are at root
        current_idx = self.list_view.rootIndex()
        current_path = Path(self.model.filePath(current_idx))
        
        if self.current_root and current_path == self.current_root:
            # Go back to Project List
            self.backRequested.emit()
        else:
            # Go up one level
            parent_idx = current_idx.parent()
            if parent_idx.isValid():
                # Ensure we don't go above system root (though logical check handles project root)
                # But wait, parent() of a folder inside root is correct.
                # If we are at project root, we handled it above.
                self.list_view.setRootIndex(parent_idx)
                self._update_breadcrumbs(current_path.parent)

    def _open_in_explorer(self):
        current_idx = self.list_view.rootIndex()
        folder_path = self.model.filePath(current_idx)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))

    def _refresh(self):
        # QFileSystemModel watches automatically, but sometimes we might want to force
        # Actually QFileSystemModel doesn't have a simple reload. 
        # But setting root path again usually works or it just works by itself.
        # Let's just re-set root index to ensure view is synced
        idx = self.list_view.rootIndex()
        self.list_view.setRootIndex(idx)

    def _enter_note(self, path: str):
        current_note = self.note_service.get_note(path) or ""
        
        w = NoteDialog("留言", current_note, self.window())
        if w.exec():
            text = w.get_text()
            self.note_service.save_note(path, text)
            self._on_item_clicked(self.list_view.currentIndex())

    def _on_item_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        path = self.model.filePath(index)
        note = self.note_service.get_note(path)
        if note:
             # Create custom info bar with styling to ensure visibility
             InfoBar.info(
                title='备注',
                content=note,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000,
                parent=self
            )

    def _show_context_menu(self, pos: QPoint):
        index = self.list_view.indexAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['card']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px;
                border-radius: 4px;
                color: {COLORS['text']};
            }}
            QMenu::item:selected {{
                background-color: {COLORS['primary']};
                color: white;
            }}
        """)
        
        if index.isValid():
            path = self.model.filePath(index)
            
            # --- Open / Explore ---
            open_action = QAction(FluentIcon.ACCEPT.icon(), "打开", self)
            open_action.triggered.connect(lambda: self._on_item_double_clicked(index))
            menu.addAction(open_action)
            
            explorer_action = QAction(FluentIcon.FOLDER.icon(), "在资源管理器中显示", self)
            explorer_action.triggered.connect(lambda: subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"', shell=True))
            menu.addAction(explorer_action)
            
            # Open With
            if not Path(path).is_dir():
                open_with_action = QAction(FluentIcon.APPLICATION.icon(), "打开方式...", self)
                open_with_action.triggered.connect(lambda: subprocess.Popen(f'rundll32.exe shell32.dll,OpenAs_RunDLL {os.path.normpath(path)}', shell=True))
                menu.addAction(open_with_action)

            menu.addSeparator()

            # Note Action
            note_action = QAction(FluentIcon.CHAT.icon(), "进入留言", self)
            note_action.triggered.connect(lambda: self._enter_note(path))
            menu.addAction(note_action)

            tag_action = QAction("设置标签", self)
            tag_action.triggered.connect(lambda: self._edit_tags(path))
            menu.addAction(tag_action)
            
            menu.addSeparator()
            
            # --- Edit Actions ---
            # Copy File (to clipboard for pasting in Explorer)
            copy_file_action = QAction(FluentIcon.COPY.icon(), "复制", self)
            copy_file_action.triggered.connect(lambda: self._copy_file_to_clipboard(path))
            menu.addAction(copy_file_action)

            # Copy Path
            copy_path_action = QAction(FluentIcon.LINK.icon(), "复制路径", self)
            copy_path_action.triggered.connect(lambda: QApplication.clipboard().setText(os.path.normpath(path)))
            menu.addAction(copy_path_action)
            
            menu.addSeparator()

            # Rename
            rename_action = QAction(FluentIcon.EDIT.icon(), "重命名", self)
            rename_action.triggered.connect(lambda: self._rename_item(index))
            menu.addAction(rename_action)

            # Delete
            delete_action = QAction(FluentIcon.DELETE.icon(), "删除", self)
            delete_action.triggered.connect(lambda: self._delete_item(index))
            menu.addAction(delete_action)

        else:
            # Background context menu
            new_folder_action = QAction(FluentIcon.ADD.icon(), "新建文件夹", self)
            new_folder_action.triggered.connect(self._create_new_folder)
            menu.addAction(new_folder_action)
            
            menu.addSeparator()

            refresh_action = QAction(FluentIcon.SYNC.icon(), "刷新", self)
            refresh_action.triggered.connect(self._refresh)
            menu.addAction(refresh_action)

            menu.addSeparator()

            explorer_action = QAction(FluentIcon.FOLDER.icon(), "在资源管理器中打开", self)
            explorer_action.triggered.connect(self._open_in_explorer)
            menu.addAction(explorer_action)

        menu.exec(self.list_view.mapToGlobal(pos))

    def _copy_file_to_clipboard(self, path: str):
        mime_data = QMimeData()
        url = QUrl.fromLocalFile(path)
        mime_data.setUrls([url])
        QApplication.clipboard().setMimeData(mime_data)

    def _rename_item(self, index: QModelIndex):
        old_name = self.model.fileName(index)
        old_path = Path(self.model.filePath(index))
        old_rel = self._rel_path_for_fs_path(str(old_path))
        
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新名称:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = old_path.parent / new_name
            try:
                os.rename(old_path, new_path)
                new_rel = self._rel_path_for_fs_path(str(new_path))
                if self.project_root and old_rel and new_rel:
                    try:
                        self._item_tags = self.tag_service.move_item(self.project_root, old_rel, new_rel)
                        self.list_view.viewport().update()
                    except Exception:
                        pass
            except Exception as e:
                # Simple error handling
                print(f"Rename failed: {e}")

    def _delete_item(self, index: QModelIndex):
        path = Path(self.model.filePath(index))
        name = path.name
        rel = self._rel_path_for_fs_path(str(path))
        is_dir = path.is_dir()
        
        # Confirm Dialog
        w = MessageBoxBase(self)
        w.titleLabel = SubtitleLabel("确认删除", w)
        w.viewLayout.addWidget(w.titleLabel)
        w.viewLayout.addWidget(BodyLabel(f"确定要永久删除 '{name}' 吗？\n此操作不可恢复！", w))
        w.yesButton.setText("删除")
        w.cancelButton.setText("取消")
        w.yesButton.setStyleSheet("QPushButton { background-color: #dc2626; color: white; border: none; } QPushButton:hover { background-color: #b91c1c; }")
        
        if w.exec():
            try:
                if is_dir:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                if self.project_root and rel:
                    try:
                        self._item_tags = self.tag_service.delete_item(self.project_root, rel, is_dir=is_dir)
                        self.list_view.viewport().update()
                    except Exception:
                        pass
            except Exception as e:
                print(f"Delete failed: {e}")

    def _create_new_folder(self):
        current_idx = self.list_view.rootIndex()
        parent_dir = Path(self.model.filePath(current_idx))
        if not parent_dir.exists():
            parent_dir = self.current_root
            
        new_name, ok = QInputDialog.getText(self, "新建文件夹", "请输入文件夹名称:", text="新建文件夹")
        if ok and new_name:
            new_path = parent_dir / new_name
            try:
                new_path.mkdir(exist_ok=False)
            except FileExistsError:
                 pass # Or show error
            except Exception as e:
                print(f"Create folder failed: {e}")
