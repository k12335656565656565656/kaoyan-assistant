"""Build a runnable standalone package for the professional knowledge workflow."""

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
PACK_DIR = ROOT / "KnowledgeBase-Standalone"
ZIP_FILE = ROOT / "KnowledgeBase-Standalone.zip"

# 清理
try:
    if PACK_DIR.exists():
        shutil.rmtree(PACK_DIR)
except:
    pass
try:
    if ZIP_FILE.exists():
        ZIP_FILE.unlink()
except:
    pass

# 创建目录
PACK_DIR.mkdir(parents=True, exist_ok=True)
(PACK_DIR / "data").mkdir(exist_ok=True)

# 核心文件
print("[1/4] Copying core files...")
core_files = {
    "app_kb.py": "app.py",           # 入口重命名
    "knowledge_base.py": "knowledge_base.py",
    "requirements_kb.txt": "requirements.txt",
    "SETUP_kb.md": "SETUP.md",
    ".env.example": ".env.example",
}
for src_name, dst_name in core_files.items():
    src = ROOT / src_name
    if src.exists():
        shutil.copy2(src, PACK_DIR / dst_name)
        print(f"    {src_name} -> {dst_name}")

# 运行模块。旧脚本只复制 knowledge_base.py，会遗漏它依赖的包。
print("[2/4] Copying workflow modules...")
for module_name in ("professional_knowledge", "repositories", "schemas", "services"):
    source_dir = ROOT / module_name
    target_dir = PACK_DIR / module_name
    shutil.copytree(
        source_dir,
        target_dir,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    print(f"    {module_name}/")

# 使用文档
print("[3/4] Copying docs...")
docs_dir = PACK_DIR / "docs"
docs_dir.mkdir(exist_ok=True)
for doc_name in (
    "knowledge-base-outsourcing.md",
    "professional_knowledge_quick_workflow.md",
    "professional_knowledge_integration.md",
):
    doc_src = ROOT / "docs" / doc_name
    if doc_src.exists():
        shutil.copy2(doc_src, docs_dir / doc_name)
        print(f"    {doc_name}")

# 打 ZIP
print("[4/4] Creating ZIP...")
with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in PACK_DIR.rglob("*"):
        if f.is_file():
            arcname = str(f.relative_to(PACK_DIR)).replace("\\", "/")
            info = zipfile.ZipInfo(arcname)
            info.flag_bits |= 0x800
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            with open(f, "rb") as src:
                zf.writestr(info, src.read())

# 统计
total = sum(1 for _ in PACK_DIR.rglob("*") if _.is_file())
size = ZIP_FILE.stat().st_size

# 清理
shutil.rmtree(PACK_DIR)

print(f"\n{'='*50}")
print(f"Package ready: {ZIP_FILE.name}")
print(f"  Files: {total}")
print(f"  Size:  {size:,} bytes ({size/1024:.0f} KB)")
print(f"\n外化解压后直接使用，详见 SETUP.md")
