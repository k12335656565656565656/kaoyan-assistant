# -*- coding: utf-8 -*-
from PyPDF2 import PdfReader
import os

# 新增的3本教辅
files = [
    '2026考研数学强化30讲-核心基础突破.pdf',
    '2026考研高等数学核心讲义-.pdf',
    '26考研概率论与数理统计强化一本通.pdf'
]

output_dir = 'txt_output'
os.makedirs(output_dir, exist_ok=True)

for f in files:
    if os.path.exists(f):
        print(f'处理: {f}')
        reader = PdfReader(f)
        print(f'  页数: {len(reader.pages)}')

        # 提取所有页面的文本
        all_text = ''
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                all_text += f'\n--- 第{i+1}页 ---\n' + text

        # 保存为txt
        txt_name = f.replace('.pdf', '.txt')
        txt_path = os.path.join(output_dir, txt_name)
        with open(txt_path, 'w', encoding='utf-8') as fp:
            fp.write(all_text)
        print(f'  已保存: {txt_path} ({len(all_text)} 字符)')

        # 打印前3页预览
        print(f'  ---前3页预览---')
        preview = ''
        for i in range(min(3, len(reader.pages))):
            preview += reader.pages[i].extract_text() or ''
        print(preview[:1000])
        print()
    else:
        print(f'文件不存在: {f}')