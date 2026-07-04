"""
ntfh VIP patch — 3 parts:
1. Hide VIP upsell (premium card skip)
2. Core crack (fake token + VIP roles + purchase page block)
3. Fake account (profile + settings display)
"""
from pathlib import Path

RESULTS = []


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").split('\n')


def _write(path: Path, lines: list[str]):
    path.write_text('\n'.join(lines), encoding="utf-8")


def _replace_method(f: Path, method_sig: str, body: str, locals_n: int, check: str = None):
    """Find method by signature, clear body, replace with new code."""
    lines = _read(f)
    for i, line in enumerate(lines):
        if line.strip().startswith('.method ') and method_sig in line:
            if check and check in ''.join(lines[i:i+15]):
                return False
            for j in range(i, len(lines)):
                if lines[j].strip() == '.end method':
                    for k in range(i + 1, j):
                        lines[k] = ''
                    lines[i + 1] = f'    .locals {locals_n}'
                    lines[j] = body + '\n.end method'
                    _write(f, lines)
                    return True
    return False


def _nop_cond(f: Path, cond_label: str, target_label: str, search_range: int = 30):
    """Find 'if-eqz REG, :target' and nop it. Searches forward from condition."""
    lines = _read(f)
    for i, line in enumerate(lines):
        if line.strip() == f'if-eqz {cond_label}, {target_label}':
            for j in range(i + 1, min(i + search_range, len(lines))):
                if target_label.rstrip(':') in lines[j] or lines[j].strip().startswith(target_label):
                    lines[i] = '    nop'
                    _write(f, lines)
                    return True
                if lines[j].strip().startswith((':', '.method', '.end')):
                    break
    return False


def _nop_cond_reverse(f: Path, cond_label: str, target_label: str, search_range: int = 600):
    """Find 'if-eqz REG, :target' by searching backwards from label."""
    lines = _read(f)
    label_line = None
    for i, line in enumerate(lines):
        if line.strip() == target_label:
            label_line = i
            break
    if label_line is None:
        return False
    for i in range(label_line - 1, max(label_line - search_range, 0), -1):
        if lines[i].strip() == f'if-eqz {cond_label}, {target_label}':
            lines[i] = '    nop'
            _write(f, lines)
            return True
    return False


# ── 1. Hide upsell ──────────────────────────────────────────────

def patch_upsell(smali_dir: Path):
    # qs4: isVip=TRUE shows become_premium card — always skip
    f = smali_dir / "qs4.smali"
    if f.exists() and _nop_cond(f, 'v3', ':cond_a'):
        RESULTS.append("  qs4: skip become_premium card")

    # q1: becomes premium card — nop the condition
    f = smali_dir / "q1.smali"
    if f.exists() and _nop_cond_reverse(f, 'v2', ':cond_14'):
        RESULTS.append("  q1: nop become_premium upsell card")


# ── 2. Core crack ───────────────────────────────────────────────

def patch_core(smali_dir: Path):
    at5 = smali_dir / "at5.smali"
    if not at5.exists():
        RESULTS.append("  [WARN] at5.smali not found")
        return

    # Fake login token
    if _replace_method(at5, 'ʾ()Ljava/lang/String;',
                       '    const-string p0, "fake_token"\n    return-object p0', 0,
                       check='fake_token'):
        RESULTS.append('  at5.ʾ() → "fake_token"')
    else:
        RESULTS.append("  at5.ʾ() already patched")

    # Roles getter → always return VIP Set
    vip_set_body = (
        '    new-instance v0, Ljava/util/HashSet;\n'
        '    invoke-direct {v0}, Ljava/util/HashSet;-><init>()V\n'
        '    const-string v1, "user-vip"\n'
        '    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n'
        '    const-string v1, "aXNQcmVtaXVt"\n'
        '    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n'
        '    return-object v0')
    if _replace_method(at5, 'ʽ()Ljava/util/Set;', vip_set_body, 2, check='user-vip'):
        RESULTS.append("  at5.ʽ() → always returns Set with user-vip + isPremium")
    else:
        RESULTS.append("  at5.ʽ() already patched")

    # Roles setter → inject user-vip
    lines = _read(at5)
    for i, line in enumerate(lines):
        if line.strip().startswith('.method ') and 'ʿ(Ljava/util/Set;)V' in line:
            if any('"user-vip"' in l for l in lines[i:i+20]):
                RESULTS.append("  at5.ʿ() already patched")
                break
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith('.locals '):
                j += 1
            if j < len(lines):
                lines[j] = '    .locals 3'
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            inject = [
                '', '    new-instance v0, Ljava/util/HashSet;',
                '    invoke-direct {v0, p1}, Ljava/util/HashSet;-><init>(Ljava/util/Collection;)V',
                '    const-string v1, "user-vip"',
                '    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z',
                '    move-result v2', '    move-object p1, v0', '',
            ]
            lines[k:k] = inject
            _write(at5, lines)
            RESULTS.append('  at5.ʿ() → inject "user-vip"')
            break

    # Block premium page navigation
    vp0 = smali_dir / "vp0.smali"
    if vp0.exists() and _replace_method(vp0, 'ﹶ(Lit3;)V', '    return-void', 0):
        RESULTS.append("  vp0.ﹶ() → no-op (purchase page blocked)")

    # isVip always true in bp7
    bp7 = smali_dir / "bp7.smali"
    if bp7.exists():
        lines = _read(bp7)
        patched = 0
        for i, line in enumerate(lines):
            if line.strip() == 'const/4 v0, 0x0':
                if (14640 < i < 14645) or (16494 < i < 16500):
                    lines[i] = '    const/4 v0, 0x1'
                    patched += 1
        if patched:
            _write(bp7, lines)
            RESULTS.append(f"  bp7: isVip always true ({patched} methods)")


# ── 3. Fake account ─────────────────────────────────────────────

def patch_fake_account(smali_dir: Path):
    # ny1: profile display name + username
    f = smali_dir / "ny1.smali"
    if f.exists():
        lines = _read(f)
        patched = False
        for i, line in enumerate(lines):
            if line.strip() == 'const v8, 0x7f110470':
                for j in range(i - 1, max(i - 10, 0), -1):
                    if '-0x49119f9b' in lines[j]:
                        for k in range(j, min(i + 15, len(lines))):
                            if 'move-result-object v8' in lines[k]:
                                for m in range(j, k + 1):
                                    lines[m] = ''
                                lines[j] = '    const-string v8, "VIP User"'
                                patched = True
                                break
                        break
                break
        for i, line in enumerate(lines):
            if line.strip() == 'const-string v6, ""' and 430 <= i <= 450:
                lines[i] = '    const-string v6, "vip_user"'
                patched = True
                break
        if patched:
            _write(f, lines)
            RESULTS.append("  ny1: profile → VIP User / vip_user")

    # sp: settings username + display name + email
    f = smali_dir / "sp.smali"
    if f.exists():
        lines = _read(f)
        patched = False
        for i, line in enumerate(lines):
            ls = line.strip()
            if ls == 'move-object v3, v5' and 15720 <= i <= 15735:
                lines[i] = '    const-string v3, "vip_user"'
                patched = True
            elif ls == 'move-object v6, v5' and 15780 <= i <= 15800:
                lines[i] = '    const-string v6, "VIP User"'
                patched = True
            elif ls == 'move-object v6, v5' and 15835 <= i <= 15850:
                lines[i] = '    const-string v6, "vip@example.com"'
                patched = True
        if patched:
            _write(f, lines)
            RESULTS.append("  sp: settings → VIP User / vip_user / vip@example.com")


# ── Main ────────────────────────────────────────────────────────

def patch(smali_dir: Path, version_info: dict = None, repo_url: str = None, **kwargs) -> list[str]:
    global RESULTS
    RESULTS = []
    print("=== ntfh VIP patch ===")
    patch_upsell(smali_dir)
    patch_core(smali_dir)
    patch_fake_account(smali_dir)
    return RESULTS if RESULTS else ["  [WARN] No patches applied"]
