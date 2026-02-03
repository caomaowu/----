# 压铸项目管理系统 (DCPM)

这是一个基于 Python + PyQt6 + Fluent Widgets 构建的现代化桌面应用程序，专为压铸行业项目管理设计。它提供了优雅的界面、极速的全文检索和智能的项目组织功能，帮助工程师和项目经理高效管理海量项目文件。

## ✨ 核心特性

- **🎨 现代化 UI 设计**: 采用 Fluent Design 风格，支持三栏式布局（侧边导航、主视图、右侧详情），界面美观、交互流畅。
- **🚀 极速全文检索**: 基于 SQLite FTS5 引擎，毫秒级搜索项目名称、客户、标签及备注。
- **📂 智能项目创建**:
  - 自动生成规范的项目编号（YY-NNN）。
  - 自动创建标准文件夹结构（3D/2D/变更记录等）。
  - 自动初始化项目元数据。
- **🏷️ 多维管理**:
  - **置顶项目**: 关注重点项目。
  - **标签系统**: 自定义标签，支持按标签筛选。
  - **最近动态**: 自动记录最近打开和创建的项目。
  - **状态追踪**: 进行中 / 已交付 / 已归档。
- **📊 数据仪表盘**: 实时统计本月新建、活跃项目及整体交付进度。

## 🛠️ 技术栈

- **语言**: Python 3.10+
- **GUI 框架**: PyQt6
- **UI 组件库**: [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
- **数据存储**: SQLite (FTS5) + JSON (元数据)
- **架构**: 领域驱动设计 (DDD) 分层架构 (UI / Services / Domain / Infra)

## 📦 安装与运行

### 前置要求

- Windows 10/11 (推荐)
- Python 3.10 或更高版本

### 1. 安装依赖

在项目根目录下运行：

```bash
pip install PyQt6 "PyQt-Fluent-Widgets[full]" platformdirs
```

### 2. 启动应用

使用 Python 模块方式运行：

```bash
python -m dcpm
```

### 3. 首次使用

1. 启动后，系统会提示选择**项目库根目录**（即存放所有项目文件夹的总目录）。
2. 选择目录后，系统会自动扫描现有文件夹并建立索引（首次扫描可能需要几秒钟）。
3. 点击右侧“新建项目”即可开始创建标准化的项目结构。

## 📂 项目结构

```text
dcpm/
├── app/            # 应用程序入口与生命周期管理
├── domain/         # 核心业务逻辑与数据模型 (Project, Rules)
├── infra/          # 基础设施层 (Config, DB, FileSystem)
├── services/       # 应用服务层 (ProjectService, IndexService)
├── ui/             # 用户界面层
│   ├── components/ # 可复用 UI 组件 (Cards, etc.)
│   ├── theme/      # 颜色与样式定义
│   ├── views/      # 主要视图 (Sidebar, RightPanel)
│   └── main_window.py # 主窗口逻辑
└── __main__.py     # 启动入口
```

