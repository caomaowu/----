from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QThread
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QGridLayout, QDialog
)


class RebuildIndexThread(QThread):
    """后台重建索引线程"""
    finished = pyqtSignal(object)  # IndexDb
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current, total

    def __init__(self, library_root: Path, parent=None):
        super().__init__(parent)
        self.library_root = library_root
        self._is_running = True

    def run(self):
        try:
            def on_progress(current: int, total: int):
                if self._is_running:
                    self.progress.emit(current, total)

            db = rebuild_index(
                self.library_root,
                include_archived=True,
                progress_callback=on_progress if self._is_running else None,
            )
            if self._is_running:
                self.finished.emit(db)
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        self._is_running = False
        self.wait(1000)
from qfluentwidgets import (
    SubtitleLabel, DropDownPushButton, RoundMenu, Action, Pivot, InfoBar, InfoBarPosition, BodyLabel, MessageBoxBase,
    PushButton, PrimaryPushButton, FluentIcon as FI
)

from dcpm.services.library_service import ProjectEntry
from dcpm.services.index_service import (
    DashboardStats,
    get_dashboard_stats,
    rebuild_index,
    search,
    toggle_pinned,
    upsert_one_project,
    delete_project_index
)
from dcpm.services.project_service import (
    create_project, delete_project_physically, edit_project_metadata,
    clear_project_cover, set_project_cover, archive_project, unarchive_project
)
from dcpm.services.note_service import NoteService
from dcpm.ui.theme.colors import COLORS
from dcpm.ui.components.project_card import ProjectCard, ProjectCardOptions
from dcpm.ui.components.cards import StatCard
from dcpm.ui.components.note_dialog import NoteDialog
from dcpm.ui.dialogs.create_project import CreateProjectDialog
from dcpm.ui.dialogs.manage_project import ManageProjectDialog
from dcpm.infra.config.user_config import load_user_config

class DashboardView(QWidget):
    projectOpened = pyqtSignal(object)  # ProjectEntry
    dataLoaded = pyqtSignal(object)     # DashboardStats
    indexRebuilt = pyqtSignal(bool)     # fts5_enabled

    def __init__(self, library_root: str, parent=None):
        super().__init__(parent)
        self._library_root = library_root
        self._all_projects: list[ProjectEntry] = []
        self._filtered_projects: list[ProjectEntry] = []
        self._view_mode = "grid"
        self._status_filter = "all"
        self._time_filter = "all"
        self._search_query = ""
        self._auto_index_attempted = False
        
        # Batch mode
        self._is_batch_mode = False
        self._selected_ids: set[str] = set()
        
        # Init Note Service if library root is available
        self._note_service = NoteService(Path(self._library_root)) if self._library_root else None

        self._init_ui()
    
    def set_library_root(self, root: str):
        self._library_root = root
        self._note_service = NoteService(Path(root)) if root else None
        self.reload_projects()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(24)

        # Header
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)

        self._title_label = QLabel("全部项目")
        self._title_label.setFont(QFont("Microsoft YaHei", 24, QFont.Weight.Bold))
        self._title_label.setStyleSheet(f"color: {COLORS['text']};")
        title_layout.addWidget(self._title_label)

        self._subtitle_label = QLabel("正在加载...")
        self._subtitle_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
        title_layout.addWidget(self._subtitle_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        # View Switcher
        self._view_switch = Pivot()
        self._view_switch.addItem("grid", "⊞ 网格", lambda: self._on_view_changed("grid"))
        self._view_switch.addItem("list", "☰ 列表", lambda: self._on_view_changed("list"))
        self._view_switch.addItem("timeline", "◷ 时间线", lambda: self._on_view_changed("timeline"))
        self._view_switch.setCurrentItem("grid")
        header_layout.addWidget(self._view_switch, 0, Qt.AlignmentFlag.AlignBottom)

        layout.addLayout(header_layout)

        # Stats Bar
        self._stats_layout = QHBoxLayout()
        self._stats_layout.setSpacing(20)
        # Placeholders
        for _ in range(4):
            self._stats_layout.addWidget(StatCard("-", "0", "-", COLORS["secondary"], 0))
        layout.addLayout(self._stats_layout)

        # Filter Bar
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(12)

        # 状态筛选下拉
        self._status_btn = DropDownPushButton("📁 全部状态", self)
        self._status_btn.setFixedHeight(40)
        status_menu = RoundMenu(parent=self._status_btn)
        status_menu.addActions([
            Action("全部状态", triggered=lambda: self.set_filter("status", "all")),
            Action("进行中", triggered=lambda: self.set_filter("status", "ongoing")),
            Action("已交付", triggered=lambda: self.set_filter("status", "delivered")),
            Action("已归档", triggered=lambda: self.set_filter("status", "archived")),
        ])
        self._status_btn.setMenu(status_menu)
        filter_layout.addWidget(self._status_btn)

        # 时间筛选下拉
        self._time_btn = DropDownPushButton("📅 全部时间", self)
        self._time_btn.setFixedHeight(40)
        self._time_menu = RoundMenu(parent=self._time_btn)
        self._time_btn.setMenu(self._time_menu)
        filter_layout.addWidget(self._time_btn)

        # 标签筛选下拉
        self._tag_btn = DropDownPushButton("🏷️ 全部标签", self)
        self._tag_btn.setFixedHeight(40)
        self._tag_menu = RoundMenu(parent=self._tag_btn)
        self._tag_btn.setMenu(self._tag_menu)
        filter_layout.addWidget(self._tag_btn)

        filter_layout.addStretch()

        # Batch Actions
        self._batch_delete_btn = PrimaryPushButton("删除选中 (0)", self)
        self._batch_delete_btn.setIcon(FI.DELETE)
        self._batch_delete_btn.clicked.connect(self._batch_delete)
        self._batch_delete_btn.hide()
        filter_layout.addWidget(self._batch_delete_btn)

        self._batch_btn = PushButton("批量管理", self)
        self._batch_btn.setIcon(FI.EDIT)
        self._batch_btn.clicked.connect(self._toggle_batch_mode)
        filter_layout.addWidget(self._batch_btn)

        layout.addLayout(filter_layout)

        # Project Scroll Area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background: transparent;")
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_container = QWidget()
        QVBoxLayout(self._grid_container).setContentsMargins(0, 0, 0, 0)

        self._scroll.setWidget(self._grid_container)
        layout.addWidget(self._scroll)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() != QEvent.Type.WindowStateChange:
            return
        if getattr(self, "_view_mode", None) != "grid":
            return
        # Delay rebuild to ensure geometry is correct
        QTimer.singleShot(0, self._rebuild_grid)

    def reload_projects(self) -> None:
        if not self._library_root:
            self._all_projects = []
            self._filtered_projects = []
            self._rebuild_grid()
            return

        include_archived = self._status_filter == "archived" or self._status_filter == "all"
        result = search(Path(self._library_root), "", include_archived=True, limit=500)

        # Auto-index check
        if (not self._auto_index_attempted) and (not result.entries):
            self._auto_index_attempted = True
            try:
                db = rebuild_index(Path(self._library_root), include_archived=True)
                self.indexRebuilt.emit(db.fts5_enabled)
                result = search(Path(self._library_root), "", include_archived=True, limit=500)
            except Exception:
                pass
        else:
            self.indexRebuilt.emit(result.fts5_enabled)

        self._all_projects = result.entries

        # Load Dashboard Stats
        try:
            stats = get_dashboard_stats(Path(self._library_root))
            self._update_stats(stats)
            self._update_filter_menus(stats)
            self.dataLoaded.emit(stats) # Notify MainWindow to update sidebar/right panel
        except Exception:
            pass

        self._apply_filter()

    def _update_stats(self, stats: DashboardStats):
        # Clear old stats
        while self._stats_layout.count():
            item = self._stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = stats.total_projects
        ongoing = stats.processing_count
        delivered = stats.completed_count
        new_this_month = stats.new_this_month

        items = [
            ("本月新建", str(new_this_month), "较上月 --", COLORS["primary"], min(1.0, new_this_month / 10)),
            ("进行中", str(ongoing), "活跃项目", COLORS["info"], min(1.0, ongoing / max(1, total))),
            ("已交付", str(delivered), "本月完成", COLORS["success"], min(1.0, delivered / max(1, total))),
            ("项目总数", str(total), "全部项目", COLORS["warning"], 1.0),
        ]

        for title, value, subtitle, color, progress in items:
            self._stats_layout.addWidget(StatCard(title, value, subtitle, color, progress))

    def _update_filter_menus(self, stats: DashboardStats):
        # Update Filter Menu (Time)
        self._time_menu.clear()
        self._time_menu.addAction(Action("全部时间", triggered=lambda: self.set_filter("time", "all")))
        for month, count in stats.month_counts[:12]:
             self._time_menu.addAction(Action(f"{month} ({count})", triggered=lambda m=month: self.set_filter("time", m)))

        # Update Filter Menu (Tags)
        self._tag_menu.clear()
        self._tag_menu.addAction(Action("全部标签", triggered=lambda: self.set_filter("tag", "all")))
        for tag, count in stats.popular_tags[:20]:
            self._tag_menu.addAction(Action(f"{tag} ({count})", triggered=lambda t=tag: self.set_filter("tag", t)))

    def set_filter(self, type_: str, value: str):
        if type_ == "status":
            self._status_filter = "all" if value == "all" else f"status:{value}"
            self._status_btn.setText("📁 全部状态" if value == "all" else {
                "ongoing": "📁 进行中", "delivered": "📁 已交付", "archived": "📁 已归档"
            }.get(value, value))
        elif type_ == "time":
            self._time_filter = value
            self._time_btn.setText("📅 全部时间" if value == "all" else f"📅 {value}")
        elif type_ == "tag":
            self._tag_filter = value
            self._tag_btn.setText("🏷️ 全部标签" if value == "all" else f"🏷️ {value}")
            
        self._apply_filter()

    # Public method for external search (e.g. from RightPanel)
    def set_search_query(self, query: str):
        self._search_query = query
        self._apply_filter()

    # Public method for external navigation (e.g. from Sidebar)
    def set_nav_filter(self, key: str):
        self._status_filter = key
        self._title_label.setText({
            "all": "全部项目",
            "pinned": "置顶项目",
            "status:ongoing": "进行中项目",
            "status:delivered": "已交付项目",
            "status:archived": "归档项目"
        }.get(key, "项目列表"))
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self._search_query.lower()
        filtered = []

        for entry in self._all_projects:
            # 1. Status / Nav Filter
            if self._status_filter != "all":
                if self._status_filter == "pinned":
                    if not entry.pinned: continue
                elif self._status_filter.startswith("status:"):
                    status = self._status_filter.split(":")[1]
                    if entry.project.status != status: continue
                elif self._status_filter.startswith("month:"):
                    month = self._status_filter.split(":")[1]
                    if entry.project.create_time.strftime("%Y-%m") != month: continue

            # 2. Top Bar Filters
            if self._time_filter != "all":
                 if entry.project.create_time.strftime("%Y-%m") != self._time_filter:
                     continue
            
            if hasattr(self, "_tag_filter") and self._tag_filter != "all":
                if self._tag_filter not in entry.project.tags:
                    continue

            # 3. Search Query - Handled by Backend now
            # We trust _all_projects contains the relevant search results
            
            # 4. Archive Hiding
            if entry.project.status == "archived":
                if self._status_filter != "status:archived":
                     continue

            filtered.append(entry)

        self._filtered_projects = filtered
        self._subtitle_label.setText(f"管理和追踪您的压铸项目，共 {len(filtered)} 个项目")
        self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        new_container = QWidget()
        new_container.setStyleSheet("background: transparent;")
        
        layout = None
        if self._view_mode == "grid":
            layout = QGridLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(24)
            cols = 3
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
            for idx, entry in enumerate(self._filtered_projects):
                options = ProjectCardOptions(
                    checkable=self._is_batch_mode,
                    checked=(entry.project.id in self._selected_ids)
                )
                card = ProjectCard(entry, options, parent=new_container)
                card.openRequested.connect(self.projectOpened.emit)
                card.pinToggled.connect(self._pin_project)
                card.manageRequested.connect(self.open_manage_project)
                card.deleteRequested.connect(self._prompt_delete_project)
                card.noteRequested.connect(self._open_project_note)
                card.checkToggled.connect(self._on_card_toggled)
                layout.addWidget(card, idx // cols, idx % cols)
            layout.setRowStretch((len(self._filtered_projects) // cols) + 1, 1)
            
        elif self._view_mode == "list":
            layout = QVBoxLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            for entry in self._filtered_projects:
                options = ProjectCardOptions(
                    compact=True,
                    checkable=self._is_batch_mode,
                    checked=(entry.project.id in self._selected_ids)
                )
                card = ProjectCard(entry, options, parent=new_container)
                card.openRequested.connect(self.projectOpened.emit)
                card.pinToggled.connect(self._pin_project)
                card.manageRequested.connect(self.open_manage_project)
                card.deleteRequested.connect(self._prompt_delete_project)
                card.checkToggled.connect(self._on_card_toggled)
                layout.addWidget(card)
            layout.addStretch()
            
        elif self._view_mode == "timeline":
            layout = QVBoxLayout(new_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            groups: dict[str, list[ProjectEntry]] = {}
            for entry in self._filtered_projects:
                key = entry.project.create_time.strftime("%Y-%m")
                groups.setdefault(key, []).append(entry)
            
            for key in sorted(groups.keys(), reverse=True):
                header = SubtitleLabel(key, new_container)
                header.setStyleSheet(f"color: {COLORS['primary']}; font-weight: bold; margin-top: 12px;")
                layout.addWidget(header)
                for entry in groups[key]:
                    card = ProjectCard(entry, ProjectCardOptions(compact=True), parent=new_container)
                    card.openRequested.connect(self.projectOpened.emit)
                    card.pinToggled.connect(self._pin_project)
                    card.manageRequested.connect(self.open_manage_project)
                    card.deleteRequested.connect(self._prompt_delete_project)
                    layout.addWidget(card)
            layout.addStretch()

        self._scroll.setWidget(new_container)
        self._grid_container = new_container

    def _on_view_changed(self, mode: str):
        self._view_mode = mode
        self._rebuild_grid()

    # --- Batch Mode ---

    def _toggle_batch_mode(self):
        self._is_batch_mode = not self._is_batch_mode
        if self._is_batch_mode:
            self._batch_btn.setText("退出管理")
            self._batch_btn.setIcon(FI.CLOSE)
            self._batch_delete_btn.show()
            self._selected_ids.clear()
            self._update_batch_ui()
            
            self._status_btn.setEnabled(False)
            self._time_btn.setEnabled(False)
            self._tag_btn.setEnabled(False)
        else:
            self._batch_btn.setText("批量管理")
            self._batch_btn.setIcon(FI.EDIT)
            self._batch_delete_btn.hide()
            self._selected_ids.clear()
            
            self._status_btn.setEnabled(True)
            self._time_btn.setEnabled(True)
            self._tag_btn.setEnabled(True)
        
        self._rebuild_grid()

    def _on_card_toggled(self, pid: str, checked: bool):
        if checked:
            self._selected_ids.add(pid)
        else:
            self._selected_ids.discard(pid)
        self._update_batch_ui()

    def _update_batch_ui(self):
        count = len(self._selected_ids)
        self._batch_delete_btn.setText(f"删除选中 ({count})")
        self._batch_delete_btn.setEnabled(count > 0)

    def _batch_delete(self):
        if not self._selected_ids:
            return
            
        count = len(self._selected_ids)
        title = "批量删除确认"
        content = f"确定要彻底删除选中的 {count} 个项目吗？\n\n这些操作将永久删除项目文件夹及其所有内容，且不可恢复！"
        
        w = MessageBoxBase(self)
        w.titleLabel = SubtitleLabel(title, w)
        w.viewLayout.addWidget(w.titleLabel)
        w.viewLayout.addWidget(BodyLabel(content, w))
        w.yesButton.setText(f"删除 {count} 个项目")
        w.cancelButton.setText("取消")
        w.yesButton.setStyleSheet("QPushButton { background-color: #dc2626; color: white; border: none; } QPushButton:hover { background-color: #b91c1c; }")
        
        if w.exec():
            success_count = 0
            errors = []
            
            # Need to find entries for IDs to get paths
            to_delete = []
            for entry in self._all_projects:
                if entry.project.id in self._selected_ids:
                    to_delete.append(entry)
            
            for entry in to_delete:
                try:
                    delete_project_index(Path(self._library_root), entry.project.id)
                    delete_project_physically(entry.project_dir)
                    success_count += 1
                except Exception as e:
                    errors.append(f"{entry.project.name}: {str(e)}")
            
            self._selected_ids.clear()
            self._is_batch_mode = False # Exit batch mode after delete
            self._batch_btn.setText("批量管理")
            self._batch_btn.setIcon(FI.EDIT)
            self._batch_delete_btn.hide()
            self._status_btn.setEnabled(True)
            self._time_btn.setEnabled(True)
            self._tag_btn.setEnabled(True)
            
            self.reload_projects()
            
            if errors:
                self._show_warning(f"删除完成，但有 {len(errors)} 个错误:\n" + "\n".join(errors[:3]))
            else:
                self._show_success(f"成功删除 {success_count} 个项目")

    # --- Actions ---

    def open_create_project(self):
        if not self._library_root:
            self._show_warning("请先在右侧选择库")
            return
        dlg = CreateProjectDialog(self)
        if dlg.exec():
            try:
                from dcpm.ui.views.settings_interface import ScanThread
                
                res = create_project(Path(self._library_root), dlg.build_request())
                try: upsert_one_project(Path(self._library_root), ProjectEntry(project=res.project, project_dir=res.project_dir))
                except: pass
                
                self.reload_projects()
                
                # Trigger incremental scan
                cfg = load_user_config()
                if cfg.shared_drive_paths:
                    self._auto_scan_thread = ScanThread(
                        Path(self._library_root), 
                        cfg.shared_drive_paths, 
                        target_project=res.project
                    )
                    self._auto_scan_thread.start()
                    
            except Exception as e:
                self._show_error(str(e))

    def open_manage_project(self, entry: ProjectEntry):
        dlg = ManageProjectDialog(entry, self)
        
        def _on_delete():
            if self._prompt_delete_project(entry):
                dlg.reject()

        dlg.deleteRequested.connect(_on_delete)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                # Logic same as before
                if dlg.is_pinned != entry.pinned:
                    toggle_pinned(Path(self._library_root), entry.project.id, dlg.is_pinned)
                
                desired = dlg.status
                is_archived_dir = "归档项目" in Path(entry.project_dir).parts
                root = Path(self._library_root)
                
                final_dir = Path(entry.project_dir)
                final_project = entry.project

                if desired == "archived" and not is_archived_dir:
                    res = archive_project(root, Path(entry.project_dir))
                    final_dir = res.project_dir
                    final_project, final_dir = edit_project_metadata(root, final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description, part_number=dlg.part_number, is_special=dlg.is_special)
                elif desired != "archived" and is_archived_dir:
                    res = unarchive_project(root, Path(entry.project_dir), status=desired)
                    final_dir = res.project_dir
                    final_project, final_dir = edit_project_metadata(root, final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description, part_number=dlg.part_number, is_special=dlg.is_special)
                else:
                    final_project, final_dir = edit_project_metadata(root, final_dir, name=dlg.name, tags=dlg.tags_list, status=desired, description=dlg.description, part_number=dlg.part_number, is_special=dlg.is_special)

                if dlg.cover_cleared:
                    final_project = clear_project_cover(final_dir)
                elif dlg.cover_source_path:
                    final_project = set_project_cover(final_dir, dlg.cover_source_path)

                upsert_one_project(root, ProjectEntry(project=final_project, project_dir=final_dir, pinned=dlg.is_pinned))
                QTimer.singleShot(0, self.reload_projects)
                
                core_changed = (
                    final_project.name != entry.project.name or
                    final_project.customer_code != entry.project.customer_code or
                    final_project.part_number != entry.project.part_number
                )
                
                if core_changed:
                    from dcpm.ui.views.settings_interface import ScanThread
                    cfg = load_user_config()
                    if cfg.shared_drive_paths:
                        self._auto_scan_thread = ScanThread(
                            Path(self._library_root), 
                            cfg.shared_drive_paths, 
                            target_project=final_project
                        )
                        self._auto_scan_thread.start()
                        
            except Exception as e:
                self._show_error(str(e))

    def _pin_project(self, pid: str, pinned: bool):
        if not self._library_root: return
        toggle_pinned(Path(self._library_root), pid, pinned)
        self.reload_projects()

    def _open_project_note(self, entry: ProjectEntry):
        if not self._note_service: return
        project_dir = entry.project_dir
        current_note = self._note_service.get_note(project_dir) or ""
        w = NoteDialog(f"项目留言: {entry.project.name}", current_note, self)
        if w.exec():
            text = w.get_text()
            self._note_service.save_note(project_dir, text)
            self._show_success("项目备注已更新")

    def _prompt_delete_project(self, entry: ProjectEntry) -> bool:
        title = "确认删除"
        content = f"确定要彻底删除项目 {entry.project.name} 吗？\n\n此操作将永久删除项目文件夹及其所有内容，且不可恢复！"
        w = MessageBoxBase(self)
        w.titleLabel = SubtitleLabel(title, w)
        w.viewLayout.addWidget(w.titleLabel)
        w.viewLayout.addWidget(BodyLabel(content, w))
        w.yesButton.setText("确认删除")
        w.cancelButton.setText("取消")
        w.yesButton.setStyleSheet("QPushButton { background-color: #dc2626; color: white; border: none; } QPushButton:hover { background-color: #b91c1c; }")
        
        if w.exec():
            try:
                delete_project_index(Path(self._library_root), entry.project.id)
                delete_project_physically(entry.project_dir)
                self.reload_projects()
                self._show_success(f"项目 {entry.project.name} 已彻底移除")
                return True
            except Exception as e:
                self._show_error(str(e))
                return False
        return False

    def rebuild_index_action(self):
        if not self._library_root: return
        
        # 防止重复点击
        if hasattr(self, '_rebuild_thread') and self._rebuild_thread and self._rebuild_thread.isRunning():
            self._show_warning("索引正在重建中，请稍候...")
            return
        
        # 显示进度提示
        self._rebuild_info_bar = InfoBar.info(
            title='正在重建索引',
            content='准备中...',
            orient=Qt.Orientation.Horizontal,
            isClosable=False,
            position=InfoBarPosition.TOP,
            duration=-1,  # 不自动关闭
            parent=self
        )
        
        # 启动后台线程
        self._rebuild_thread = RebuildIndexThread(Path(self._library_root), self)
        self._rebuild_thread.finished.connect(self._on_rebuild_finished)
        self._rebuild_thread.error.connect(self._on_rebuild_error)
        self._rebuild_thread.progress.connect(self._on_rebuild_progress)
        self._rebuild_thread.start()

    def _on_rebuild_progress(self, current: int, total: int):
        if hasattr(self, '_rebuild_info_bar') and self._rebuild_info_bar:
            self._rebuild_info_bar.contentLabel.setText(f'正在索引 {current}/{total} 个项目...')
            self._rebuild_info_bar.adjustSize()

    def _on_rebuild_finished(self, db):
        # 关闭进度提示
        if hasattr(self, '_rebuild_info_bar') and self._rebuild_info_bar:
            self._rebuild_info_bar.close()
            self._rebuild_info_bar = None
        
        self.indexRebuilt.emit(db.fts5_enabled)
        self.reload_projects()
        self._show_success(f"本地索引数据库已成功更新 (FTS5: {'启用' if db.fts5_enabled else '未启用'})")
        
        # 清理线程
        if hasattr(self, '_rebuild_thread') and self._rebuild_thread:
            self._rebuild_thread.deleteLater()
            self._rebuild_thread = None

    def _on_rebuild_error(self, err: str):
        # 关闭进度提示
        if hasattr(self, '_rebuild_info_bar') and self._rebuild_info_bar:
            self._rebuild_info_bar.close()
            self._rebuild_info_bar = None
        
        self._show_error(f"重建索引失败: {err}")
        
        # 清理线程
        if hasattr(self, '_rebuild_thread') and self._rebuild_thread:
            self._rebuild_thread.deleteLater()
            self._rebuild_thread = None

    def _show_success(self, msg):
        InfoBar.success(title='成功', content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)

    def _show_error(self, msg):
        InfoBar.error(title='错误', content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=3000, parent=self)

    def _show_warning(self, msg):
        InfoBar.warning(title='提示', content=msg, orient=Qt.Orientation.Horizontal, isClosable=True, position=InfoBarPosition.TOP, duration=2000, parent=self)
