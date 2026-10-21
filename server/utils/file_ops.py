import os
import re
import json

def atomic_write_json(filepath, data):
    """Write JSON data atomically using temp file + os.replace"""
    tmp = filepath + f'.{os.getpid()}.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)

def sanitize_filename(name):
    name = os.path.basename(name or "file")
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", name).strip()
    return name or "file"

def unique_attachment_name(dir_path, filename):
    """같은 제품에 같은 이름의 파일을 두 번 올려도 기존 파일을 덮어쓰지 않도록,
    이미 있는 이름이면 뒤에 (2), (3)... 을 붙인다."""
    fname = sanitize_filename(filename)
    base, ext = os.path.splitext(fname)
    candidate = fname
    i = 1
    while os.path.exists(os.path.join(dir_path, candidate)):
        i += 1
        candidate = "%s(%d)%s" % (base, i, ext)
    return candidate
