"""
parse_apk.py — 解析 APK/XAPK 元数据（不依赖 Java/apktool）

从 AndroidManifest.xml（Binary AXML）提取:
  - package（包名）
  - versionCode（版本号）
  - versionName（版本名）
  - label（应用名称）
"""

import re
import struct
import zipfile
from pathlib import Path

# AXML chunk types
CHUNK_STRING_POOL = 0x0001
CHUNK_RESOURCE_MAP = 0x0180
CHUNK_START_NAMESPACE = 0x0100
CHUNK_END_NAMESPACE = 0x0101
CHUNK_START_TAG = 0x0102
CHUNK_END_TAG = 0x0103
CHUNK_TEXT = 0x0104

# Known android: attribute resource IDs
ATTR_VERSION_CODE = 0x0101021b
ATTR_VERSION_NAME = 0x0101021c


def _unpack(fmt, data, offset=0):
    size = struct.calcsize(fmt)
    return struct.unpack_from(fmt, data, offset)[0], offset + size


def _parse_string_pool(data, chunk_start, verbose=False):
    """Parse string pool starting from the chunk type field."""
    _, offset = _unpack('<H', data, chunk_start)  # chunk_type
    header_size, offset = _unpack('<H', data, offset)
    chunk_size, offset = _unpack('<I', data, offset)
    string_count, offset = _unpack('<I', data, offset)
    style_count, offset = _unpack('<I', data, offset)
    flags, offset = _unpack('<I', data, offset)
    strings_start, offset = _unpack('<I', data, offset)
    styles_start, offset = _unpack('<I', data, offset)

    is_utf8 = (flags & 0x100) != 0
    sorted_flag = (flags & 0x200) != 0

    if verbose:
        print(f"  [DBG]   header_size={header_size}, string_count={string_count}, style_count={style_count}", flush=True)
        print(f"  [DBG]   flags=0x{flags:04x} (utf8={is_utf8}), strings_start={strings_start}", flush=True)

    # Skip to string offsets
    offset = chunk_start + header_size

    # Read string offsets
    string_offsets = []
    for _ in range(string_count):
        so, offset = _unpack('<I', data, offset)
        string_offsets.append(so)

    # String data starts at chunk_start + strings_start
    string_data_base = chunk_start + strings_start

    strings = []
    for so in string_offsets:
        str_start = string_data_base + so
        s, _ = _read_axml_string(data, str_start, is_utf8)
        strings.append(s)

    if verbose:
        preview = [s for s in strings[:8] if s]
        print(f"  [DBG]   parsed {len(strings)} strings, first few: {preview}", flush=True)

    # End of string pool
    pool_end = chunk_start + chunk_size

    return strings, pool_end


def _read_axml_string(data, offset, is_utf8):
    """Read a null-terminated string from the string pool."""
    if is_utf8:
        # UTF-8: 2 bytes for character count, then UTF-8 bytes, null terminated
        cc, offset = _unpack('<H', data, offset)
        # Some implementations use variable-length encoding
        # Let me try a different approach - scan for null terminator
        end = data.index(b'\x00', offset)
        s = data[offset:end].decode('utf-8', errors='replace')
        return s, end + 1
    else:
        # UTF-16: 2 bytes for character count, then UTF-16LE bytes, null terminated (2 bytes)
        cc, offset = _unpack('<H', data, offset)
        # Actually in AXML, UTF-16 strings use 2 bytes for char count
        byte_len = cc * 2
        raw = data[offset:offset + byte_len]
        s = raw.decode('utf-16-le', errors='replace')
        return s, offset + byte_len + 2  # +2 for null terminator


def parse_apk_metadata(apk_path, verbose=False):
    """从 APK 解析元数据，返回 dict。"""
    with zipfile.ZipFile(apk_path) as z:
        names = z.namelist()
        if verbose:
            print(f"  [DBG] ZIP entries ({len(names)}):", flush=True)
            for n in names[:10]:
                print(f"    {n}", flush=True)
            if len(names) > 10:
                print(f"    ... and {len(names)-10} more", flush=True)
        for name in names:
            if name == 'AndroidManifest.xml':
                if verbose:
                    print(f"  [DBG] Found AndroidManifest.xml, size={z.getinfo(name).file_size}", flush=True)
                manifest_data = z.read(name)
                return _parse_axml(manifest_data, verbose=verbose)
        if verbose:
            print("  [DBG] AndroidManifest.xml NOT FOUND in ZIP", flush=True)
        return {'package': '', 'version_code': 0, 'version_name': '', 'label': ''}


def _parse_axml(data, verbose=False):
    """解析 Binary AXML 格式的 AndroidManifest.xml。"""
    result = {'package': '', 'version_code': 0, 'version_name': '', 'label': ''}

    if len(data) < 8:
        if verbose:
            print(f"  [DBG] AXML data too short: {len(data)} bytes", flush=True)
        return result

    magic, offset = _unpack('<I', data, 0)
    if magic != 0x00080003:
        if verbose:
            print(f"  [DBG] Not AXML magic: 0x{magic:08x}", flush=True)
        return result

    file_size, offset = _unpack('<I', data, offset)
    if verbose:
        print(f"  [DBG] AXML file_size={file_size}, actual_data={len(data)}", flush=True)

    strings = []
    offset = 8  # start after header
    chunk_count = 0

    while offset < file_size and offset < len(data):
        if offset + 8 > len(data):
            if verbose:
                print(f"  [DBG] Truncated chunk at offset {offset}", flush=True)
            break
        chunk_type, _ = _unpack('<H', data, offset)
        chunk_count += 1

        if chunk_type == CHUNK_STRING_POOL:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: STRING_POOL at 0x{offset:x}", flush=True)
            strings, offset = _parse_string_pool(data, offset, verbose=verbose)
        elif chunk_type == CHUNK_RESOURCE_MAP:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: RESOURCE_MAP at 0x{offset:x}", flush=True)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        elif chunk_type == CHUNK_START_TAG:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: START_TAG at 0x{offset:x}", flush=True)
            _parse_start_tag(data, offset, strings, result, verbose=verbose)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        elif chunk_type == CHUNK_END_TAG:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: END_TAG at 0x{offset:x}", flush=True)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        elif chunk_type == CHUNK_TEXT:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: TEXT at 0x{offset:x}", flush=True)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        elif chunk_type in (CHUNK_START_NAMESPACE, CHUNK_END_NAMESPACE):
            if verbose:
                ns_name = "START_NAMESPACE" if chunk_type == CHUNK_START_NAMESPACE else "END_NAMESPACE"
                print(f"  [DBG] Chunk #{chunk_count}: {ns_name} at 0x{offset:x}", flush=True)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        else:
            if verbose:
                print(f"  [DBG] Chunk #{chunk_count}: UNKNOWN (0x{chunk_type:04x}) at 0x{offset:x}", flush=True)
            if offset + 8 > len(data):
                break
            try:
                chunk_size, _ = _unpack('<I', data, offset + 4)
                offset = offset + chunk_size
            except:
                break
            try:
                _, offset = _unpack('<H', data, offset)  # chunk_type
                hdr_size, offset = _unpack('<H', data, offset)
                chunk_size, offset = _unpack('<I', data, offset)
                offset = offset + chunk_size - 8
            except:
                break

    # Fallback: try to find strings in raw data
    if not result['package']:
        if verbose:
            print(f"  [DBG] Trying raw text fallback for package...", flush=True)
        raw = data.decode('utf-8', errors='replace')
        m = re.search(r'package[=:]\s*["\']?([a-zA-Z0-9_.]+)["\']?', raw)
        if m:
            if verbose:
                print(f"  [DBG] Raw fallback found package={m.group(1)}", flush=True)
            result['package'] = m.group(1)
        elif verbose:
            print(f"  [DBG] Raw fallback also failed", flush=True)

    if verbose:
        print(f"  [DBG] Parse result: package={result['package']!r}, version={result['version_name']!r}, code={result['version_code']}", flush=True)
    return result


def _parse_start_tag(data, offset, strings, result, verbose=False):
    """解析 StartTag chunk，提取 manifest 元素属性。"""
    _, offset = _unpack('<H', data, offset)  # chunk_type
    header_size, offset = _unpack('<H', data, offset)
    chunk_size, offset = _unpack('<I', data, offset)
    line_number, offset = _unpack('<I', data, offset)
    comment_idx, offset = _unpack('<I', data, offset)

    ns_idx, offset = _unpack('<I', data, offset)
    name_idx, offset = _unpack('<I', data, offset)

    # Handle header_size padding (same fix as axml.js)
    if header_size > 24:
        offset += (header_size - 24)

    # Element name (e.g., "manifest")
    elem_name = strings[name_idx] if name_idx >= 0 and name_idx < len(strings) else ''

    if verbose:
        print(f"  [DBG]   element='{elem_name}' (name_idx={name_idx}, ns_idx={ns_idx})", flush=True)

    # Not the manifest element, skip
    if elem_name.lower() != 'manifest':
        if verbose:
            print(f"  [DBG]   skipping non-manifest element", flush=True)
        return

    flags, offset = _unpack('<H', data, offset)
    attr_count, offset = _unpack('<H', data, offset)
    class_attr, offset = _unpack('<I', data, offset)

    if verbose:
        print(f"  [DBG]   manifest attr_count={attr_count}", flush=True)

    for i in range(attr_count):
        ns_idx_attr, offset = _unpack('<I', data, offset)
        name_idx_attr, offset = _unpack('<I', data, offset)
        raw_value_idx, offset = _unpack('<I', data, offset)

        # Typed value
        val_size, offset = _unpack('<H', data, offset)
        val_res0, offset = _unpack('<B', data, offset)
        val_type, offset = _unpack('<B', data, offset)
        val_data, offset = _unpack('<I', data, offset)

        attr_name = strings[name_idx_attr] if 0 <= name_idx_attr < len(strings) else f'?idx={name_idx_attr}'

        if val_type == 0x03:
            if 0 <= raw_value_idx < len(strings):
                val = strings[raw_value_idx]
            else:
                val = ''
        elif val_type == 0x10:
            val = val_data
        elif val_type == 0x11 or val_type == 0x01:
            val = 'true' if val_data == -1 or val_data == 0xFFFFFFFF else 'false'
        else:
            val = str(val_data)

        if verbose:
            print(f"  [DBG]   attr[{i}]: {attr_name}={val!r} (type=0x{val_type:02x}, data=0x{val_data:x})", flush=True)

        if attr_name == 'package':
            result['package'] = str(val)
        elif attr_name == 'versionCode':
            try:
                result['version_code'] = int(val)
            except (ValueError, TypeError):
                result['version_code'] = 0
        elif attr_name == 'versionName':
            result['version_name'] = str(val)


def find_app_dir(package_name):
    """根据包名查找 apps/ 下对应的 app 目录。"""
    base = Path(__file__).resolve().parent.parent / 'apps'
    for app_dir in base.iterdir():
        if not app_dir.is_dir():
            continue
        app_json = app_dir / 'app.json'
        if app_json.exists():
            import json
            cfg = json.loads(app_json.read_text(encoding='utf-8'))
            if cfg.get('package') == package_name:
                return app_dir.name
    return None


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('apk_path', help='APK 文件路径')
    parser.add_argument('--find-app', action='store_true', help='同时匹配 app 目录')
    args = parser.parse_args()

    info = parse_apk_metadata(args.apk_path)
    if args.find_app:
        info['app'] = find_app_dir(info['package'])

    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
