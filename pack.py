"""自动打包脚本 - 生成部署用 ZIP（含高校热度预测引擎）"""
import zipfile, os, shutil
from pathlib import Path

ROOT = Path(__file__).parent
PACK_DIR = ROOT / "KaoyanRAG-v4.0"
ZIP_FILE = ROOT / "KaoyanRAG-v4.2.zip"

# 清理（如果文件被占用则跳过）
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
for d in ["data/corpus", "data/corpus_demo", "data/katex", "skills", "templates", "test_data", "kaoyan_predict/auth"]:
    (PACK_DIR / d).mkdir(parents=True, exist_ok=True)

print("[1/5] Copying core files...")
core_files = ["app.py", "admin.py", "knowledge_base.py", "kaoyan_predict.py", "recommend.py", "requirements.txt", "SETUP.md", "DEPLOY.md"]
bat_files = ["启动.bat", "启动考研RAG_Streamlit.bat"]
for f in core_files + bat_files:
    src = ROOT / f
    if src.exists():
        shutil.copy2(src, PACK_DIR / f)

print("[2/5] Copying knowledge base...")
corpus = ROOT / "data" / "corpus"
count = 0
for f in sorted(corpus.iterdir()):
    if f.suffix.lower() == ".md":
        shutil.copy2(f, PACK_DIR / "data" / "corpus" / f.name)
        count += 1

# 拷贝 demo corpus
demo_corpus = ROOT / "data" / "corpus_demo"
for f in sorted(demo_corpus.iterdir()):
    if f.is_file():
        shutil.copy2(f, PACK_DIR / "data" / "corpus_demo" / f.name)
print(f"    {count} docs + {len(list(demo_corpus.iterdir()))} demo docs copied")

print("[3/5] Copying Skills...")
skills_dir = ROOT / "skills"
for skill in skills_dir.iterdir():
    if skill.is_dir() and not skill.name.startswith("_"):
        dest = PACK_DIR / "skills" / skill.name
        shutil.copytree(skill, dest, dirs_exist_ok=True)
        print(f"    {skill.name}")

print("[4/5] Copying prediction engine...")
pred_dir = ROOT / "kaoyan_predict"
pred_count = 0
for f in pred_dir.rglob("*"):
    if f.is_file() and "node_modules" not in str(f):
        rel = f.relative_to(pred_dir)
        dest = PACK_DIR / "kaoyan_predict" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)
        pred_count += 1
print(f"    {pred_count} files")

print("[5/5] Copying templates...")
templates = ROOT / "templates"
for f in templates.iterdir():
    if f.is_file():
        shutil.copy2(f, PACK_DIR / f.name)

# 拷贝演示测试数据
test_data = ROOT / "test_data"
for f in test_data.iterdir():
    if f.name.startswith("hallucination_tests_demo"):
        shutil.copy2(f, PACK_DIR / "test_data" / f.name)

# 拷贝英语真题 JSON
essay_json = ROOT / "data" / "essay_topics.json"
if essay_json.exists():
    shutil.copy2(essay_json, PACK_DIR / "data" / "essay_topics.json")
    print("    essay_topics.json copied")

# 拷贝英语真题图片目录
essay_imgs = ROOT / "data" / "英语真题图片"
if essay_imgs.exists():
    dest = PACK_DIR / "data" / "英语真题图片"
    dest.mkdir(parents=True, exist_ok=True)
    img_count = 0
    for f in essay_imgs.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)
            img_count += 1
    print(f"    {img_count} essay images copied")

# 打 ZIP（UTF-8 编码，跨平台兼容 Linux unzip）
print(f"\nCreating {ZIP_FILE.name}...")
with zipfile.ZipFile(ZIP_FILE, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in PACK_DIR.rglob("*"):
        if f.is_file():
            arcname = str(f.relative_to(PACK_DIR)).replace("\\", "/")
            info = zipfile.ZipInfo(arcname)
            info.flag_bits |= 0x800          # 标记 UTF-8 文件名
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3            # Unix
            with open(f, "rb") as src:
                zf.writestr(info, src.read())

# 统计
total = sum(1 for _ in PACK_DIR.rglob("*") if _.is_file())
size = ZIP_FILE.stat().st_size

# 清理临时目录
shutil.rmtree(PACK_DIR)

print(f"\n{'='*50}")
print(f"Package ready: {ZIP_FILE.name}")
print(f"  Files: {total}")
print(f"  Size:  {size:,} bytes ({size/1024:.0f} KB)")
print(f"\nSend this file. Recipient unzips and reads SETUP.md")
