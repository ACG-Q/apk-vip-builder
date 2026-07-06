"""
ntfh VIP patch — for ntfh 2.72.4

1. bt5.ʽ() → always return Set with "user-vip" (core roles getter)
2. bt5.ʿ(Set) → inject "user-vip" into stored roles
3. vp0.ﹶ() → return-void (block purchase page navigation)
"""
from pathlib import Path

RESULTS = []


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").split("\n")


def _write(path: Path, lines: list[str]):
    path.write_text("\n".join(lines), encoding="utf-8")


def _replace_method(f: Path, method_sig: str, body: str, locals_n: int, check: str = None):
    """Find method by signature, clear body, replace with new code."""
    lines = _read(f)
    for i, line in enumerate(lines):
        if line.strip().startswith(".method ") and method_sig in line:
            if check and check in "".join(lines[i : i + 15]):
                return False
            for j in range(i, len(lines)):
                if lines[j].strip() == ".end method":
                    for k in range(i + 1, j):
                        lines[k] = ""
                    lines[i + 1] = f"    .locals {locals_n}"
                    lines[j] = body + "\n.end method"
                    _write(f, lines)
                    return True
    return False


def patch(smali_dir: Path, version_info: dict = None, repo_url: str = None, **kwargs) -> list[str]:
    global RESULTS
    RESULTS = []
    print("=== ntfh VIP patch ===")

    bt5 = smali_dir / "bt5.smali"
    if not bt5.exists():
        RESULTS.append("  [WARN] bt5.smali not found")
        return RESULTS

    # 1. bt5.ʽ() → always return Set with "user-vip" + "aXNQcmVtaXVt"
    vip_set_body = (
        "    new-instance v0, Ljava/util/HashSet;\n"
        "    invoke-direct {v0}, Ljava/util/HashSet;-><init>()V\n"
        '    const-string v1, "user-vip"\n'
        "    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n"
        '    const-string v1, "aXNQcmVtaXVt"\n'
        "    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z\n"
        "    return-object v0"
    )
    if _replace_method(bt5, "ʽ()Ljava/util/Set;", vip_set_body, 2, check="user-vip"):
        RESULTS.append("  bt5.getter() -> Set with user-vip + isPremium")
    else:
        RESULTS.append("  bt5.getter() already patched")

    # 2. bt5.ʿ(Set) → inject "user-vip"
    lines = _read(bt5)
    for i, line in enumerate(lines):
        if line.strip().startswith(".method ") and "ʿ(Ljava/util/Set;)V" in line:
            if any('"user-vip"' in l for l in lines[i : i + 20]):
                RESULTS.append("  bt5.ʿ() already patched")
                break
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith(".locals "):
                j += 1
            if j < len(lines):
                lines[j] = "    .locals 3"
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            inject = [
                "",
                "    new-instance v0, Ljava/util/HashSet;",
                "    invoke-direct {v0, p1}, Ljava/util/HashSet;-><init>(Ljava/util/Collection;)V",
                '    const-string v1, "user-vip"',
                "    invoke-interface {v0, v1}, Ljava/util/Set;->add(Ljava/lang/Object;)Z",
                "    move-result v2",
                "    move-object p1, v0",
                "",
            ]
            lines[k:k] = inject
            _write(bt5, lines)
            RESULTS.append('  bt5.setter() -> inject "user-vip"')
            break

    # 3. vp0.ﹶ() -> return-void (block purchase page)
    vp0 = smali_dir / "vp0.smali"
    if vp0.exists() and _replace_method(vp0, "ﹶ(Lit3;)V", "    return-void", 0):
        RESULTS.append("  vp0.nav() -> no-op")
    else:
        RESULTS.append("  vp0 not found or already patched")

    for r in RESULTS:
        print(f"  {r}")
    return RESULTS
