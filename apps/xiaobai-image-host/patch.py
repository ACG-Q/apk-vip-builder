"""
patch.py — VIP persistent + PrimeDialogFragment blocker for XiaoBai Image Host

Patches:
1. setPrimeType() sput-object -> const-string "1" (persist VIP)
2. AES class catch widened -> return "" on error (safety)
3. wv0.smali no-op (blocks PrimeDialogFragment navigation)
"""
from pathlib import Path

SMALI_DIR = None
RESULTS = []


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").split('\n')


def _write(path: Path, lines: list[str]):
    path.write_text('\n'.join(lines), encoding="utf-8")


def patch_setter_force(f, method_name: str, field: str, fake_value: str):
    """Force setter to always write fake_value (sput-object -> const-string)."""
    lines = _read(f)
    in_method = False
    for i, line in enumerate(lines):
        ls = line.strip()
        if ls.startswith('.method ') and method_name in ls:
            in_method = True
            continue
        if in_method and ls.startswith('.end method'):
            break
        if in_method and ls.startswith('sput-object') and field in ls:
            lines[i] = f'    const-string p1, "{fake_value}"'
            RESULTS.append(f"  {method_name} forces \"{fake_value}\" (line {i+1})")
            break
    _write(f, lines)


def patch_wv0_blocker(f: Path):
    """Make wv0.smali's navigation helper a no-op (blocks PrimeDialogFragment)."""
    lines = _read(f)
    in_method = False
    for i, line in enumerate(lines):
        ls = line.strip()
        if ls.startswith('.method '):
            in_method = True
        if in_method and ls.startswith('.locals '):
            lines[i] = '    .locals 0'
        if in_method and ls.startswith(('    sget-object', '    invoke-', '    move-result',
                                         '    const ', '    const/', '    .line', '    invoke-virtual',
                                         '    new-instance', '    iput-object', '    sput-object')):
            lines[i] = ''
        if in_method and ls == '.end method':
            break
    RESULTS.append("  wv0.smali PrimeDialogFragment navigation blocked (no-op)")
    _write(f, lines)


def patch_aes_catch(smali_dir: Path):
    """Widen AES catch to Exception; replace catch handlers with 'return ""'."""
    for f in sorted(smali_dir.glob("*.smali")):
        content = f.read_text(encoding="utf-8", errors="replace")
        if "AESCrypt" not in content or "Base64;->decode" not in content:
            continue
        lines = content.split('\n')
        changed = False
        for i, line in enumerate(lines):
            if '.catch Ljava/io/UnsupportedEncodingException;' in line:
                lines[i] = line.replace(
                    'Ljava/io/UnsupportedEncodingException;',
                    'Ljava/lang/Exception;'
                )
                changed = True
        catch_starts = [i for i, line in enumerate(lines) if line.strip() == ':catch_0']
        for i in reversed(catch_starts):
            k = i + 1
            while k < len(lines) and not lines[k].strip().startswith('.end method'):
                k += 1
            catch_body = '\n'.join(lines[i:k])
            if 'throw' in catch_body and 'return-object' not in catch_body:
                indent = '    '
                new_body = [
                    f'{indent}:catch_0',
                    f'{indent}move-exception p0',
                    '',
                    f'{indent}const-string v0, ""',
                    '',
                    f'{indent}return-object v0',
                ]
                lines[i:k] = new_body
                changed = True
        if changed:
            f.write_text('\n'.join(lines), encoding="utf-8")
            RESULTS.append(f"  AES class catch widened -> return empty string (file: {f.name})")
            return
    RESULTS.append("  [WARN] AES class not found for catch fix")


def patch(smali_dir: Path, version_info: dict, repo_url: str, **kwargs) -> list[str]:
    global SMALI_DIR, RESULTS
    SMALI_DIR = smali_dir
    RESULTS = []
    print("=== VIP persistent + PrimeDialogFragment blocker ===")

    ur = smali_dir / "com" / "lwjlol" / "imagehosting" / "persistence" / "UserRegistry.smali"

    if not ur.exists():
        return ["  [ERR] UserRegistry.smali not found"]

    # VIP persistent: force setPrimeType to always write "1"
    patch_setter_force(ur, 'setPrimeType(', '_primeType', '1')

    # AES safety net: catch all exceptions instead of just UnsupportedEncodingException
    patch_aes_catch(smali_dir)

    # PrimeDialogFragment blocker
    wv0 = smali_dir / "wv0.smali"
    patch_wv0_blocker(wv0)

    return RESULTS if RESULTS else ["  [WARN] No patches applied"]
