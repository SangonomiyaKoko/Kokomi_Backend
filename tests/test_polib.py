import polib
from pathlib import Path

def mo_to_po(mo_file_path: str, po_file_path: str = None):
    """
    将 .mo 文件读取并生成对应的 .po 文件

    Args:
        mo_file_path (str): .mo 文件路径
        po_file_path (str, optional): 输出 .po 文件路径，如果不提供，默认同目录同名 .po
    """
    mo_file = Path(mo_file_path)

    if not mo_file.exists():
        raise FileNotFoundError(f"{mo_file} 不存在")
    if po_file_path is None:
        po_file_path = mo_file.with_suffix(".po")
    mo = polib.mofile(str(mo_file))
    po = polib.POFile()
    po.metadata = mo.metadata
    for entry in mo:
        po.append(entry)
    po.save(str(po_file_path))
    print(f"已生成 po 文件: {po_file_path}")

mo_to_po(r"C:\Users\MaoYu\Desktop\live_26.0\Live\latest\global.mo")