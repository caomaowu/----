from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QModelIndex, QPoint, QDir, QUrl, QMimeData
from PyQt6.QtGui import QDesktopServices, QAction, QFileSystemModel
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListView, QMenu, QApplication, QFrame, QInputDialog,
    QStackedWidget
)
from qfluentwidgets import (
    BreadcrumbBar, FluentIcon, TransparentToolButton, 
    MessageBoxBase, SubtitleLabel, BodyLabel, InfoBar, InfoBarPosition,
    Pivot
)

from dcpm.ui.theme.colors import COLORS
from dcpm.services.note_service import NoteService
from dcpm.services.tag_service import TagService
from dcpm.ui.components.note_dialog import NoteDialog
from dcpm.ui.views.inspection_timeline import InspectionTimeline
from dcpm.ui.components.file_delegate import FileItemDelegate
from dcpm.ui.dialogs.tag_dialog import TagDialog

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
        
        # Let's try to find the index under mouse position
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
        self.list_view.setAcceptDrops(False) 
        self.list_view.setDragEnabled(True) 
        self.list_view.setDragDropMode(QListView.DragDropMode.DragOnly) 
        
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
        if not path or not path.exists():
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
                self.list_view.setRootIndex(parent_idx)
                self._update_breadcrumbs(current_path.parent)

    def _open_in_explorer(self):
        current_idx = self.list_view.rootIndex()
        folder_path = self.model.filePath(current_idx)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))

    def _refresh(self):
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
