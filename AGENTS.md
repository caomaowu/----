# AGENTS.md - 压铸项目管理系统 (DCPM)

> 本文件面向 AI 编程助手，旨在快速了解本项目架构和开发规范。

## 项目概述

**压铸项目管理系统 (DCPM)** 是一个基于 Python + PyQt6 + Fluent Widgets 构建的现代化桌面应用程序，专为压铸行业项目管理设计。

### 核心功能
- 项目创建与管理（自动生成项目编号、标准文件夹结构）
- 极速全文检索（基于 SQLite FTS5）
- 多维管理（置顶、标签、状态追踪、最近动态）
- 沉浸式文件浏览（内置文件管理器，支持拖放、快捷键）
- **文件/文件夹标签系统**（支持对子文件夹与文件打标签，系统级索引检索，为后续智能化准备）
- 数据仪表盘（统计、热门标签、最近活动）

### 技术栈
- **语言**: Python 3.10+
- **GUI 框架**: PyQt6
- **UI 组件库**: [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
- **数据存储**: SQLite (FTS5 全文索引) + JSON (项目元数据)
- **架构模式**: 领域驱动设计 (DDD) 分层架构

---

## 项目结构

```text
dcpm/
├── __init__.py           # 版本号定义
├── __main__.py           # 启动入口
├── app/
│   └── main.py           # 应用程序生命周期、全局异常处理
├── domain/               # 领域层：核心业务逻辑与数据模型
│   ├── project.py        # Project 数据类定义
│   ├── rules.py          # 项目编号规则、月份解析、路径清理
├── infra/                # 基础设施层：数据持久化与系统交互
│   ├── config/
│   │   └── user_config.py    # 用户配置管理（库根目录路径）
│   ├── db/
│   │   └── index_db.py       # SQLite 数据库操作、FTS5 索引
│   └── fs/
│       ├── layout.py         # 项目文件夹结构创建
│       └── metadata.py       # 项目元数据 JSON 读写
├── services/             # 应用服务层：业务用例编排
│   ├── index_service.py      # 索引管理、搜索、统计
│   ├── library_service.py    # 项目库扫描、ProjectEntry
│   ├── note_service.py       # 文件备注服务
│   ├── project_service.py    # 项目 CRUD、归档/解档、封面管理
│   └── tag_service.py        # 文件/文件夹标签管理（持久化、索引同步）
└── ui/                   # 用户界面层
    ├── main_window.py        # 主窗口、三栏布局协调
    ├── theme/
    │   └── colors.py         # 配色方案
    ├── components/
    │   ├── cards.py          # 统计卡片、阴影卡片基类
    │   ├── note_dialog.py    # 备注编辑弹窗
    │   ├── project_card.py   # 项目卡片组件（网格/紧凑模式）
    └── views/
        ├── sidebar.py        # 左侧导航栏
        ├── right_panel.py    # 右侧快捷操作面板
        └── file_browser.py   # 文件浏览器（面包屑、图标视图）
```

---

## 架构设计

### 分层架构（DDD）

1. **Domain 层** (`domain/`)
   - 定义核心业务实体：`Project` 数据类
   - 业务规则：`ProjectId` 生成规则、月份格式验证、文件夹名称清理
   - 无外部依赖，纯业务逻辑

2. **Infrastructure 层** (`infra/`)
   - **Config**: 用户配置存储在 `%LOCALAPPDATA%/dcpm/config.json`
   - **Database**: SQLite 数据库位于 `{library_root}/.pm_system/index.sqlite`
     - 使用 FTS5 虚拟表实现全文检索
     - 支持项目表、文件表、备注表、文件/文件夹标签表
   - **FileSystem**: 项目元数据存储为 `.project.json`

3. **Services 层** (`services/`)
   - 编排领域对象和基础设施完成业务用例
   - `ProjectService`: 项目创建、编辑、归档、删除
   - `IndexService`: 索引重建、搜索、统计、置顶管理
   - `LibraryService`: 扫描项目库目录
   - `NoteService`: 文件备注增删改查

4. **UI 层** (`ui/`)
   - 三栏式布局：Sidebar (260px) | Main Content (弹性) | RightPanel (320px)
   - 使用 PyQt 信号/槽机制进行组件通信
   - Fluent Design 风格：圆角、阴影、渐变背景

---

## 启动与运行

### 安装依赖

```bash
pip install -r requirements.txt
```

依赖内容：
```
PyQt6
PyQt6-Fluent-Widgets
```

### 启动应用

```bash
# 开发模式运行
python -m dcpm

# 冒烟测试（不显示窗口）
python -m dcpm --smoke
```

### 首次使用

1. 启动后，系统会提示选择**项目库根目录**（存放所有项目文件夹的总目录）
2. 选择后自动扫描现有文件夹并建立索引
3. 配置存储在 `%LOCALAPPDATA%/dcpm/config.json`

---

## 数据存储规范

### 项目目录结构

```text
{library_root}/
├── .pm_system/               # 系统数据（索引、缓存）
│   ├── index.sqlite          # SQLite 数据库
│   └── cache/
├── 2024-03/                  # 月份目录 (YYYY-MM 格式)
│   └── PRJ-202403-001_客户_项目名称/
│       ├── .project.json     # 项目元数据
│       ├── .pm_cover/        # 封面图片存储
│       ├── 01_工程数据/
│       ├── 02_技术文档/
│       ├── 03_项目管理/
│       ├── 04_试模现场/
│       ├── 05_交付物/
│       └── 06_其它/
└── 归档项目/                 # 归档项目存放目录
```

### 项目元数据格式 (.project.json)

```json
{
  "id": "PRJ-202403-001",
  "name": "项目名称",
  "customer": "客户名称",
  "create_time": "2024-03-15T09:30:00",
  "status": "ongoing",
  "tags": ["压铸", "模具"],
  "item_tags": {
    "01_工程数据": ["常用"],
    "01_工程数据/3305壳体3.stp": ["第一版", "常用"]
  },
  "customer_code": null,
  "part_number": null,
  "description": null,
  "cover_image": ".pm_cover/cover.jpg"
}
```

---

## 文件/文件夹标签系统

### 交互入口

- 在文件浏览器中对文件/文件夹右键，选择“设置标签”
- 标签以小胶囊形式显示在条目下方（最多展示 2 个，超出显示 `+N`）

### 检索与索引

- 标签写入 `.project.json` 的 `item_tags`
- 索引库会将标签写入 SQLite 的 `item_tags` 表，并在 FTS5 可用时写入 `item_tag_fts`，因此在全局搜索中可直接搜索“第一版/第二版/常用”等标签

---

## 代码规范

### Python 代码风格

- **类型注解**: 强制使用类型提示，特别是公共 API
  ```python
  def create_project(library_root: Path, req: CreateProjectRequest) -> CreateProjectResult:
  ```

- **导入排序**: 
  1. 标准库 (`__future__`, `datetime`, `pathlib` 等)
  2. 第三方库 (`PyQt6`, `qfluentwidgets`)
  3. 项目内部模块

- **字符串引号**: 代码中使用双引号，文档字符串使用三引号

- **中文注释**: 项目主要使用中文注释和文档字符串

### 命名约定

| 类型 | 命名风格 | 示例 |
|------|----------|------|
| 类 | PascalCase | `ProjectCard`, `IndexService` |
| 函数/方法 | snake_case | `create_project`, `search_project_ids` |
| 常量 | UPPER_SNAKE_CASE | `PRIMARY_COLOR`, `COLORS` |
| 私有属性 | 单下划线前缀 | `_library_root`, `_grid_container` |
| 信号 | snake_case + pyqtSignal | `openRequested`, `pinToggled` |

### UI 开发规范

1. **颜色使用**: 统一从 `dcpm.ui.theme.colors.COLORS` 字典获取
   ```python
   from dcpm.ui.theme.colors import COLORS
   color = COLORS['primary']  # #E65100
   ```

2. **Fluent 组件**: 优先使用 PyQt-Fluent-Widgets 组件
   - 弹窗：`MessageBoxBase` 替代 `QMessageBox`
   - 消息提示：`InfoBar` 替代原生对话框
   - 按钮：`PrimaryPushButton`, `PushButton`, `DropDownPushButton`

3. **样式表**: 组件级样式使用内联字符串，避免外部 CSS 文件

---

## 关键模式与实现

### 1. 全局异常处理

```python
# dcpm/app/main.py
def exception_hook(exctype, value, tb):
    traceback_str = "".join(traceback.format_exception(exctype, value, tb))
    print(traceback_str, file=sys.stderr)
    if QApplication.instance():
        parent = QApplication.activeWindow()
        if parent:
            InfoBar.error(title='Critical Error', content=str(value), parent=parent)
    sys.exit(1)

sys.excepthook = exception_hook
```

### 2. 数据库连接管理

```python
# 使用上下文管理风格
db = open_index_db(library_root)
conn = connect(db)
try:
    rows = search_project_ids(conn, query, limit, db.fts5_enabled)
finally:
    conn.close()
```

### 3. 缓存机制

`ProjectCard` 使用类级字典缓存封面图片和颜色，限制缓存大小防止内存泄漏：

```python
class ProjectCard(ShadowCard):
    _bg_pixmap_cache: dict[tuple[str, int, int, int], QPixmap] = {}
    _bg_color_cache: dict[tuple[str, int], QColor] = {}
```

### 4. 信号/槽通信

```python
# 定义信号
class ProjectCard(ShadowCard):
    openRequested = pyqtSignal(object)      # ProjectEntry
    pinToggled = pyqtSignal(str, bool)      # project_id, pinned
    deleteRequested = pyqtSignal(object)    # ProjectEntry

# 连接信号
card.openRequested.connect(self._open_project)
card.pinToggled.connect(self._pin_project)
```

### 5. 延迟弹窗（封面预览）

使用 QTimer 实现长按预览，避免误触发：

```python
def mousePressEvent(self, event):
    if self._cover_path():
        if self._cover_preview_timer is None:
            self._cover_preview_timer = QTimer(self)
            self._cover_preview_timer.setSingleShot(True)
            self._cover_preview_timer.timeout.connect(self._open_cover_preview)
        self._cover_preview_timer.start(220)  # 220ms 延迟
```

---

## 测试策略

目前项目**无自动化测试套件**。测试主要通过：

1. **冒烟测试**: `python -m dcpm --smoke` 验证应用能正常启动
2. **手动测试**: 各功能模块的人工验证
3. **异常处理**: 全局异常捕获防止程序崩溃

建议添加测试时考虑：
- `domain/rules.py` 中的解析函数适合单元测试
- `infra/` 层的文件操作需要临时目录夹具
- `services/` 层需要 mock 数据库连接

---

## 常见问题与调试

### 1. 数据库锁定
SQLite WAL 模式已启用，支持并发读写。如出现锁定：
- 检查是否有其他进程持有连接未关闭
- 查看 `{library_root}/.pm_system/index.sqlite-wal` 文件

### 2. 索引失效
如果搜索结果异常，使用右侧面板「重建索引」功能刷新数据库。

### 3. UI 刷新问题
- 网格视图使用「替换容器」策略：`self._scroll.setWidget(new_container)`
- 避免直接修改布局，防止已销毁对象引用错误

### 4. 文件拖放无效
确保：
- `FileBrowser.setAcceptDrops(True)` 已启用
- `QListView.setAcceptDrops(False)` 让事件冒泡到父组件

---

## 扩展开发指南

### 添加新的项目状态

1. 修改 `domain/project.py` 中的 status 字段验证（如需要）
2. 更新 UI 中的筛选按钮：
   - `main_window.py`: `_status_btn` 菜单项
   - `sidebar.py`: 状态筛选导航按钮
3. 更新数据库查询逻辑（如需要特殊处理）

### 添加新的文件夹模板

修改 `infra/fs/layout.py`:

```python
def create_project_folders(project_dir: Path) -> None:
    folders = [
        "01_工程数据",
        "02_技术文档",
        # 添加新文件夹...
    ]
```

### 添加新的统计指标

1. 修改 `infra/db/index_db.py`:
   - 添加 `get_new_stats()` 函数
2. 更新 `services/index_service.py`:
   - 修改 `DashboardStats` 数据类
   - 更新 `get_dashboard_stats()` 函数
3. 更新 `ui/main_window.py`:
   - 修改 `_update_stats()` 方法添加新的 StatCard

---

## 智能标签系统

### 概述

智能标签系统用于自动识别和管理项目文件中的元数据标签，支持**自动提取**和**人工添加**两种模式。

### 自动标签规则

系统从文件名中自动提取以下标签：

| 类别 | 识别规则 | 示例 | 提取标签 |
|-----|---------|------|---------|
| 版本 | `第[一二三四五12345]版` / `[vV]\d+` | `模具_第一版.pdf` | `第一版` 🔵 |
| 版本 | `[rR]ev\.?[A-Z0-9]` | `设计_Rev.A.dwg` | `Rev.A` 🔵 |
| 类型 | 关键词匹配 | `流道渣包图.stp` | `流道渣包图` 🟢 |
| 类型 | 文件扩展名 | `report.pdf` | `PDF文档` 🟢 |
| 阶段 | 关键词匹配 | `初版_工艺.docx` | `初版` 🟠 |

### 快捷标签预设

系统预设以下快捷标签（可在标签编辑弹窗中一键添加）：

- `第一版`、`第二版`（版本类）
- `模具图`、`流道渣包图`、`模流报告`、`压铸计算参数`（文件类型类）

### 数据库表结构

```sql
-- 文件标签表
CREATE TABLE file_tags(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    tag_category TEXT,      -- version/type/stage/custom
    color TEXT,
    source TEXT,            -- 'auto' 或 'manual'
    created_time TEXT,
    UNIQUE(file_path, tag_name)
);

-- 禁用的自动标签表（用户删除的自动标签，避免重新生成）
CREATE TABLE disabled_auto_tags(
    file_path TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    disabled_time TEXT,
    PRIMARY KEY(file_path, tag_name)
);
```

### 使用方式

**添加/编辑标签**：
1. 在文件浏览器中右键点击文件
2. 选择「编辑标签...」
3. 在弹窗中可：
   - 删除现有标签（自动标签会被禁用，不再自动出现）
   - 输入新标签名添加
   - 点击快捷标签一键添加

**按标签筛选**：
1. 进入项目文件浏览器
2. 顶部显示该项目所有标签及其使用次数
3. 点击标签进行筛选（可多选）

### 相关文件

- `domain/smart_tags.py` - 标签规则引擎、预设标签定义
- `services/tag_service.py` - 标签服务（自动提取、CRUD、智能推荐）
- `ui/components/tag_badge.py` - 标签徽章组件、标签筛选栏
- `ui/components/tag_editor.py` - 标签编辑弹窗

---

## 版本历史

当前版本: **0.1.3** (2026-02-03)

主要更新：
- 沉浸式文件浏览器（拖放支持、右键菜单、快捷键）
- 项目删除功能（物理删除 + 索引清理）
- 高级筛选（状态、月份、标签）
- 全局异常捕获机制

详细变更见 `CHANGELOG.md`
