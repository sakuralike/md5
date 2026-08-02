# 桌面压缩包测试样本

本目录中的二进制样本全部由 [`scripts/generate-desktop-archive-fixtures.py`](../../../scripts/generate-desktop-archive-fixtures.py) 使用合成数据生成，不包含真实文件、真实密码或个人信息。

- 合成密码：`synthetic-password`
- 合成条目：`folder/synthetic-content.txt`
- `encrypted-valid.zip`：AES-256 加密 ZIP。
- `encrypted-valid.7z`：含加密头的 7z。

重新生成：

```powershell
python -m pip install -r scripts/desktop-fixtures-requirements.txt
python scripts/generate-desktop-archive-fixtures.py
```
