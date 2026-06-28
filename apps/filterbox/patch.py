"""
patch.py — FilterBox VIP smali patching (Phase A/B/C/D)
"""

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

SMALI_DIR = None


def is_std_lib(rel):
    return rel.startswith(("com\\", "android\\", "androidx\\", "kotlin\\", "java\\", "javax\\"))


def find_vip_interface():
    for f in sorted(SMALI_DIR.rglob("*.smali")):
        content = f.read_text(encoding="utf-8", errors="replace")
        if ".class public interface abstract" not in content:
            continue
        if re.search(r'\.method.*abstract.*\(\)I', content) and \
           re.search(r'\.method.*abstract.*\(\)Z', content) and \
           re.search(r'\.method.*abstract.*\(J\)Z', content):
            m = re.search(r'\.class.*L([^;]+);', content)
            if m:
                return m.group(1)
    return None


def find_implementations(iface_name):
    result = []
    for f in sorted(SMALI_DIR.rglob("*.smali")):
        content = f.read_text(encoding="utf-8", errors="replace")
        if f".implements L{iface_name};" in content:
            result.append(f)
    return result


def find_state_class(iface_name):
    for f in sorted(SMALI_DIR.rglob("*.smali")):
        rel = str(f.relative_to(SMALI_DIR))
        if is_std_lib(rel):
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        if f"L{iface_name};" not in content:
            continue

        lines = content.split('\n')
        for i, line in enumerate(lines):
            if not re.match(r'^\.method\s+.*\bstatic\b.*\(\)I\s*$', line):
                continue
            body = []
            for j in range(i + 1, min(i + 300, len(lines))):
                if lines[j].strip().startswith('.method ') or lines[j].strip().startswith('.end method'):
                    break
                body.append(lines[j])
            body_text = '\n'.join(body)

            calls = re.findall(rf'L{iface_name};->(\w+)\(([^)]*)\)([^\s]+)', body_text)
            calls_j = set()
            calls_jz = False
            for cname, cparams, cret in calls:
                if cparams == '' and cret == 'J':
                    calls_j.add(cname)
                elif cparams == 'J' and cret == 'Z':
                    calls_jz = True

            if len(calls_j) >= 2 and calls_jz:
                return f, i
    return None, None


def find_purchase_dialog(state_dir):
    for f in sorted(state_dir.glob("*.smali")):
        if "$" in f.name:
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        if "Lcom/google/android/material/bottomsheet/b;" not in content or "new-instance" not in content:
            continue
        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_s = line.strip()
            if line_s.startswith('.method ') and ' final ' in line_s and line_s.endswith('(I)V'):
                return f, i
    return None, None


def patch_method_at(content, start_line, new_body):
    lines = content.split('\n')
    end = None
    for i in range(start_line + 1, len(lines)):
        if re.match(r'^\.end\s+method\s*$', lines[i].strip()):
            end = i
            break
    if end is None:
        return content, False
    new_lines = lines[:start_line] + [lines[start_line], new_body.strip(), '.end method'] + lines[end + 1:]
    return '\n'.join(new_lines), True


def patch_by_sig(content, params_sig, return_type, new_body, static_only=False):
    lines = content.split('\n')
    suffix = '(' + params_sig + ')' + return_type
    count = 0
    i = 0
    while i < len(lines):
        line_s = lines[i].strip()
        if not line_s.startswith('.method '):
            i += 1
            continue
        if static_only and ' static ' not in line_s and not line_s.startswith('.method static '):
            i += 1
            continue
        if not line_s.endswith(suffix):
            i += 1
            continue

        end = None
        for j in range(i + 1, len(lines)):
            if re.match(r'^\.end\s+method\s*$', lines[j].strip()):
                end = j
                break
        if end is None:
            i += 1
            continue

        new_lines = lines[:i] + [lines[i], new_body.strip(), '.end method'] + lines[end + 1:]
        lines = new_lines
        count += 1
        i = i + 3

    return '\n'.join(lines), count


def find_and_patch_files():
    patches_applied = []

    state_ret = """    .locals 1
    const/4 v0, 0x3
    return v0"""
    false_ret = """    .locals 1
    const/4 v0, 0x0
    return v0"""
    active_ret = """    .locals 1
    const/4 v0, 0x1
    return v0"""

    iface = find_vip_interface()
    if not iface:
        print("  [ERR] VIP interface not found")
        return patches_applied
    print(f"  Interface: L{iface};")

    impl_files = find_implementations(iface)
    state_info = find_state_class(iface)

    for p in impl_files:
        content = p.read_text(encoding="utf-8", errors="replace")
        content, c1 = patch_by_sig(content, '', 'Z', active_ret)
        content, c2 = patch_by_sig(content, '', 'I', state_ret)
        if c1 or c2:
            p.write_text(content, encoding="utf-8")
            patches_applied.append(f"  Patched: {p.relative_to(SMALI_DIR)} (impl: ()Z + ()I)")
        else:
            patches_applied.append(f"  [SKIP] {p.relative_to(SMALI_DIR)} (no matching methods)")

    state_file, state_line = state_info
    if state_file:
        rel = state_file.relative_to(SMALI_DIR)
        content = state_file.read_text(encoding="utf-8", errors="replace")
        content, ok1 = patch_method_at(content, state_line, state_ret)
        content, c2 = patch_by_sig(content, 'I', 'Z', false_ret, static_only=True)
        if ok1:
            state_file.write_text(content, encoding="utf-8")
            patches_applied.append(f"  Patched: {rel} (state: ()I + {c2}x (I)Z)")
        else:
            patches_applied.append(f"  [ERR] {rel} (state method not found)")

        purchase_noop = """    .locals 0
    return-void"""
        dialog_file, dialog_line = find_purchase_dialog(state_file.parent)
        if dialog_file:
            content = dialog_file.read_text(encoding="utf-8", errors="replace")
            content, ok = patch_method_at(content, dialog_line, purchase_noop)
            if ok:
                dialog_file.write_text(content, encoding="utf-8")
                patches_applied.append(f"  Patched: {dialog_file.relative_to(SMALI_DIR)} (purchase dialog suppressed)")
            else:
                patches_applied.append(f"  [ERR] {dialog_file.relative_to(SMALI_DIR)} (purchase dialog method not found)")
        else:
            patches_applied.append("  [WARN] Purchase dialog VM not found")

    return patches_applied


def add_vip_settings(version_info, repo_url):
    print("\n=== Phase D: Add VIP version info to settings ===")
    ver = version_info.get("version", "unknown")
    build_time = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary_text = f"{ver} VIP build{build_time}"

    settings_builder = None
    for f in sorted(SMALI_DIR.rglob("*.smali")):
        rel = str(f.relative_to(SMALI_DIR))
        if is_std_lib(rel) or "$" in f.name:
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        if 'const-string' in content and ' APK"' in content and 'new-array' in content:
            settings_builder = f
            break

    if not settings_builder:
        print("  [WARN] Settings builder not found")
        return []

    sdir = settings_builder.parent
    print(f"  Settings builder: {settings_builder.relative_to(SMALI_DIR)}")

    listener_file = sdir / "vip_github.smali"
    if not listener_file.exists():
        listener_smali = """\
.class public final LA3/vip_github;
.super Ljava/lang/Object;
.source "SourceFile"
# interfaces
.implements Landroid/view/View$OnClickListener;
# instance fields
.field public final a:Ly3/k0;
# direct methods
.method public constructor <init>(Ly3/k0;)V
    .locals 0
    invoke-direct {p0}, Ljava/lang/Object;-><init>()V
    iput-object p1, p0, LA3/vip_github;->a:Ly3/k0;
    return-void
.end method
# virtual methods
.method public final onClick(Landroid/view/View;)V
    .locals 3
    iget-object v0, p0, LA3/vip_github;->a:Ly3/k0;
    iget-object v0, v0, LP1/d;->d:LI1/c;
    new-instance v1, Landroid/content/Intent;
    const-string v2, "android.intent.action.VIEW"
    invoke-direct {v1, v2}, Landroid/content/Intent;-><init>(Ljava/lang/String;)V
    const-string v2, "REPO_URL"
    invoke-static {v2}, Landroid/net/Uri;->parse(Ljava/lang/String;)Landroid/net/Uri;
    move-result-object v2
    invoke-virtual {v1, v2}, Landroid/content/Intent;->setData(Landroid/net/Uri;)Landroid/content/Intent;
    invoke-virtual {v0, v1}, Landroid/content/Context;->startActivity(Landroid/content/Intent;)V
    return-void
.end method""".replace("REPO_URL", repo_url)
        listener_file.write_text(listener_smali, encoding="utf-8")
        print(f"  Listener created: {listener_file.relative_to(SMALI_DIR)}")
    else:
        print(f"  Listener exists: {listener_file.relative_to(SMALI_DIR)}")

    apktool_dir = SMALI_DIR.parent
    res_vals = apktool_dir / "res" / "values"
    strings_xml = res_vals / "strings.xml"
    public_xml = res_vals / "public.xml"

    if not any("vip_version_title" in l for l in strings_xml.read_text(encoding="utf-8").split('\n')):
        s_content = strings_xml.read_text(encoding="utf-8")
        s_content = s_content.replace('</resources>',
            f'    <string name="vip_version_title">软件版本</string>\n'
            f'    <string name="vip_version_summary">{summary_text}</string>\n'
            '</resources>')
        strings_xml.write_text(s_content, encoding="utf-8")
        print(f"  Strings added: {summary_text}")

    if not any("vip_version_title" in l for l in public_xml.read_text(encoding="utf-8").split('\n')):
        p_content = public_xml.read_text(encoding="utf-8")
        p_content = p_content.replace('</resources>',
            '<public type="string" name="vip_version_title" id="0x7f12044a" />\n'
            '<public type="string" name="vip_version_summary" id="0x7f12044b" />\n'
            '</resources>')
        public_xml.write_text(p_content, encoding="utf-8")
        print(f"  Public.xml entries added")

    content = settings_builder.read_text(encoding="utf-8", errors="replace")

    vip_item_code = """\
    new-instance v1, Ls2/b;

    invoke-direct {v1, v4}, Ls2/b;-><init>(LP1/f;)V

    const v11, 0x7f12044a

    const/4 v12, 0x0

    new-array v12, v12, [Ljava/lang/Object;

    invoke-virtual {v1, v11, v12}, Ls2/a;->u0(I[Ljava/lang/Object;)V

    const v11, 0x7f12044b

    const/4 v12, 0x0

    new-array v12, v12, [Ljava/lang/Object;

    invoke-virtual {v1, v11, v12}, Ls2/a;->t0(I[Ljava/lang/Object;)V

    new-instance v11, LA3/vip_github;

    invoke-direct {v11, v4}, LA3/vip_github;-><init>(Ly3/k0;)V

    invoke-virtual {v1, v11}, Ls2/b;->v0(Landroid/view/View$OnClickListener;)V"""

    old_null = """    const/16 v0, 0x1d

    const/4 v1, 0x0

    aput-object v1, v10, v0"""

    new_slot = vip_item_code + """

    aput-object v1, v10, v0

    const/4 v1, 0x0

    const/16 v0, 0x1e

    aput-object v1, v10, v0"""

    if old_null not in content:
        print("  [WARN] Null slot not found in settings builder")
        return []

    content = content.replace('const/16 v10, 0x1e', 'const/16 v10, 0x1f', 1)
    content = content.replace(old_null, new_slot, 1)
    settings_builder.write_text(content, encoding="utf-8")
    print(f"  Settings patched with VIP version item")
    print("  OK")
    return [f"  Settings patched: {settings_builder.relative_to(SMALI_DIR)}"]


def patch(smali_dir: Path, version_info: dict, repo_url: str) -> list[str]:
    global SMALI_DIR
    SMALI_DIR = smali_dir

    print("=== Patching smali for VIP ===")
    patches = find_and_patch_files()
    for p in patches:
        print(f"  {p}")
    if not patches:
        print("  [WARN] No patches applied. Check smali file paths.")
    else:
        print(f"  Total: {len(patches)} files patched")

    try:
        patches += add_vip_settings(version_info, repo_url)
    except Exception as e:
        print(f"  [WARN] Phase D failed: {e}")

    return patches
