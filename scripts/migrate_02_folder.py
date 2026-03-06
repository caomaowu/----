import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dcpm.infra.config.user_config import load_user_config
from dcpm.infra.fs.metadata import read_project_metadata, write_project_metadata

def migrate_folders():
    print("=== 开始批量重命名文件夹 ===")
    
    config = load_user_config()
    if not config.library_root:
        print("错误: 未找到项目库根目录配置，请先运行软件配置库路径。")
        return

    root = Path(config.library_root)
    if not root.exists():
        print(f"错误: 库根目录不存在: {root}")
        return

    old_name = "02_模流报告"
    new_name = "02_模流报告及数据收集"
    
    count_renamed = 0
    count_skipped = 0
    count_meta_updated = 0
    
    # 遍历年份月份目录
    for month_dir in root.iterdir():
        if not month_dir.is_dir() or month_dir.name.startswith("."):
            continue
            
        # 遍历项目目录
        for project_dir in month_dir.iterdir():
            if not project_dir.is_dir():
                continue
                
            old_path = project_dir / old_name
            new_path = project_dir / new_name
            
            meta_path = project_dir / ".project.json"
            
            # 1. 文件夹重命名
            renamed = False
            if old_path.exists():
                if new_path.exists():
                    print(f"跳过: {project_dir.name} - 目标文件夹已存在")
                    count_skipped += 1
                else:
                    try:
                        old_path.rename(new_path)
                        print(f"重命名: {project_dir.name}/{old_name} -> {new_name}")
                        count_renamed += 1
                        renamed = True
                    except Exception as e:
                        print(f"错误: 无法重命名 {project_dir.name}: {e}")
                        count_skipped += 1
            
            # 2. 更新元数据 (.project.json 中的 item_tags)
            if meta_path.exists():
                try:
                    p = read_project_metadata(meta_path)
                    updated_tags = {}
                    needs_save = False
                    
                    for k, v in p.item_tags.items():
                        # key 是相对路径，如 "02_模流报告/report.pdf"
                        # 统一使用正斜杠
                        k_norm = k.replace("\\", "/")
                        
                        if k_norm == old_name:
                            # 刚好是对文件夹打标签
                            updated_tags[new_name] = v
                            needs_save = True
                        elif k_norm.startswith(f"{old_name}/"):
                            # 对子文件打标签
                            new_k = f"{new_name}/{k_norm[len(old_name)+1:]}"
                            updated_tags[new_k] = v
                            needs_save = True
                        else:
                            updated_tags[k] = v
                    
                    if needs_save:
                        # 更新 Project 对象并保存
                        # 由于 Project 是 frozen dataclass，我们需要利用 replace 或者重新构造
                        # 但 metadata.py 中有 update_project_metadata，不过它只支持部分字段
                        # 这里我们直接构造字典写入，或者利用 dataclasses.replace (如果可用)
                        # 为了稳妥，我们直接修改 item_tags 字典并重新构造 Project 对象
                        
                        # 但 Project 是 frozen 的，无法直接修改属性。
                        # 我们可以利用 infra/fs/metadata.py 中的 write_project_metadata
                        # 我们需要创建一个新的 Project 实例
                        from dataclasses import replace
                        new_p = replace(p, item_tags=updated_tags)
                        write_project_metadata(meta_path, new_p)
                        print(f"  已更新元数据: {project_dir.name}")
                        count_meta_updated += 1
                        
                except Exception as e:
                    print(f"警告: 读取/更新元数据失败 {project_dir.name}: {e}")

    print("-" * 40)
    print(f"完成! 重命名文件夹: {count_renamed}, 跳过: {count_skipped}, 更新元数据: {count_meta_updated}")
    print("注意: 请在软件中执行【重建索引】以确保搜索功能正常。")

if __name__ == "__main__":
    migrate_folders()
