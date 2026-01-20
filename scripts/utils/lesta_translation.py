import json
import polib
import os
import shutil
import time


cwd = os.getcwd()

def is_chinese(text):
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def check_ship_name_translation(data_file_path: str, mo_file_path: str):
    with open(data_file_path, 'r', encoding='utf-8') as f:
        product_data = json.load(f)
    backup_file = os.path.join(cwd, 'temp', 'backup', f'ship_name_lesta_{int(time.time())}.json')
    shutil.copy(data_file_path, backup_file)
    mo = polib.mofile(mo_file_path)
    mo_dict = {entry.msgid: entry.msgstr for entry in mo}
    for product_id, info in product_data.items():
        ship_cn = info.get('ship_name', {}).get('cn', '')
        if (
            'ARP' in ship_cn or 
            ship_cn.endswith(' CLR') or 
            ship_cn.endswith(' B') or 
            ship_cn.endswith(' Test')
        ):
            continue
        if not is_chinese(ship_cn):
            index = info.get('index', '')
            mo_key = f"IDS_{index}"
            translated = mo_dict.get(mo_key, ship_cn)
            if ship_cn == translated:
                continue
            ship_cn = ship_cn + ' ' * max(20-len(ship_cn), 0)
            print(f"ID: {product_id}  {ship_cn} ->  {translated}")
            info['ship_name']['cn'] = translated
    with open(data_file_path, 'w', encoding='utf-8') as f:
        json.dump(product_data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    '''
    https://github.com/DDFantasyV/MK_RU_Data/tree/main/Live/latest
    '''
    check_ship_name_translation(
        data_file_path=os.path.join(cwd, 'data', 'json', 'ship_name_lesta.json'), 
        mo_file_path=os.path.join(cwd, 'temp', 'global.mo')
    )