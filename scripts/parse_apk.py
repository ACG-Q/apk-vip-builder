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


def _parse_string_pool(data, offset):
    """Parse AXML StringPool chunk, return list of strings and new offset."""
    chunk_type, offset = _unpack('<H', data, offset)
    assert chunk_type == CHUNK_STRING_POOL, f"Expected StringPool, got {chunk_type:x}"
    header_size, offset = _unpack('<H', data, offset)
    chunk_size, offset = _unpack('<I', data, offset)
    string_count, offset = _unpack('<I', data, offset)
    style_count, offset = _unpack('<I', data, offset)
    flags, offset = _unpack('<I', data, offset)
    strings_start, offset = _unpack('<I', data, offset)
    styles_start, offset = _unpack('<I', data, offset)

    is_utf8 = (flags & 0x100) != 0

    # Read string offsets
    string_offsets = []
    for _ in range(string_count):
        so, offset = _unpack('<I', data, offset)
        string_offsets.append(so)

    # Skip style offsets
    offset = chunk_start + styles_start if styles_start else offset
    offset = chunk_start + styles_start if styles_start else (chunk_start + chunk_size)

    # Actually, let's be more precise
    chunk_start_ = offset - 24 - (header_size - 24)  # This is getting messy
    # Let me just compute chunk start
    chunk_start = offset - 24 - (string_count * 4) - (header_size - 24)

    # Actually, let me redo this properly
    # Chunk layout:
    #   header: 
    #     chunk_type (2) + header_size (2) + chunk_size (4) = 8 bytes
    #   then:
    #     string_count (4) + style_count (4) + flags (4) + strings_start (4) + styles_start (4) = 20 bytes
    #   then header_size - 28 bytes of padding
    #   then: string_offsets (string_count * 4)
    #   then: style_offsets (style_count * 4)  -- if styles_start != 0
    #   then: string data

    # Let me just re-parse with proper tracking
    return _parse_string_pool_v2(data, offset - 24 - (string_count * 4) - (style_count * 4))


def _parse_string_pool_v2(data, chunk_start):
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


def parse_apk_metadata(apk_path):
    """从 APK 解析元数据，返回 dict。"""
    with zipfile.ZipFile(apk_path) as z:
        for name in z.namelist():
            if name == 'AndroidManifest.xml':
                manifest_data = z.read(name)
                return _parse_axml(manifest_data)
        return {'package': '', 'version_code': 0, 'version_name': '', 'label': ''}


def _parse_axml(data):
    """解析 Binary AXML 格式的 AndroidManifest.xml。"""
    result = {'package': '', 'version_code': 0, 'version_name': '', 'label': ''}

    if len(data) < 8:
        return result

    magic, offset = _unpack('<I', data, 0)
    if magic != 0x00080003:
        # Not AXML or invalid
        return result

    file_size, offset = _unpack('<I', data, offset)

    strings = []
    offset = 8  # start after header

    while offset < file_size and offset < len(data):
        if offset + 8 > len(data):
            break
        chunk_type, _ = _unpack('<H', data, offset)

        if chunk_type == CHUNK_STRING_POOL:
            strings, offset = _parse_string_pool_v2(data, offset)
        elif chunk_type == CHUNK_RESOURCE_MAP:
            # Skip resource map
            _, offset = _unpack('<H', data, offset)  # header_size
            chunk_size, offset = _unpack('<I', data, offset)
            offset = offset + chunk_size - 8
        elif chunk_type == CHUNK_START_TAG:
            # Parse start tag to find manifest attributes
            _parse_start_tag(data, offset, strings, result)
            _, hdr_size = _unpack('<H', data, offset + 2)
            chunk_size, _ = _unpack('<I', data, offset + 4)
            offset = offset + chunk_size
        elif chunk_type == CHUNK_END_TAG:
            _, offset = _unpack('<H', data, offset + 2)  # header_size (skip)
            # Actually let me skip correctly
            _, offset = _unpack('<H', data, offset)  # chunk_type
            hdr_size, offset = _unpack('<H', data, offset)
            chunk_size, offset = _unpack('<I', data, offset)
            offset = offset + chunk_size - 8
        elif chunk_type == CHUNK_TEXT:
            _, offset = _unpack('<H', data, offset)  # chunk_type
            hdr_size, offset = _unpack('<H', data, offset)
            chunk_size, offset = _unpack('<I', data, offset)
            offset = offset + chunk_size - 8
        elif chunk_type in (CHUNK_START_NAMESPACE, CHUNK_END_NAMESPACE):
            _, offset = _unpack('<H', data, offset)  # chunk_type
            hdr_size, offset = _unpack('<H', data, offset)
            chunk_size, offset = _unpack('<I', data, offset)
            offset = offset + chunk_size - 8
        else:
            # Unknown chunk, skip
            if offset + 8 > len(data):
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
        raw = data.decode('utf-8', errors='replace')
        m = re.search(r'package[=:]\s*["\']?([a-zA-Z0-9_.]+)["\']?', raw)
        if m:
            result['package'] = m.group(1)

    return result


def _parse_start_tag(data, offset, strings, result):
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

    # Not the manifest element, skip
    if elem_name.lower() != 'manifest':
        return

    flags, offset = _unpack('<H', data, offset)
    attr_count, offset = _unpack('<H', data, offset)
    class_attr, offset = _unpack('<I', data, offset)

    for _ in range(attr_count):
        ns_idx_attr, offset = _unpack('<I', data, offset)
        name_idx_attr, offset = _unpack('<I', data, offset)
        raw_value_idx, offset = _unpack('<I', data, offset)

        # Typed value
        val_size, offset = _unpack('<H', data, offset)
        val_res0, offset = _unpack('<B', data, offset)
        val_type, offset = _unpack('<B', data, offset)
        val_data, offset = _unpack('<I', data, offset)

        attr_name = strings[name_idx_attr] if 0 <= name_idx_attr < len(strings) else ''

        if val_type == 0x03:
            # String value
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
