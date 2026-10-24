
#!/usr/bin/env python3
"""
Linux-native installer for quran-player.

Usage:
    python install.py                   # incremental install / update
    python install.py --clean           # wipe install (keep config), fresh install
    python install.py --dry-run         # preview changes
    python install.py --uninstall       # remove install (keep config)
    python install.py --uninstall --purge   # remove everything
    python install.py --no-conky        # skip conky widget installation
    python install.py --verbose         # log every copy decision

Installs under $HOME. No root required.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "quran-player"
SOURCE_DIR = Path(__file__).resolve().parent
MIN_PYTHON = (3, 9)

APP_FILES = [
    # Daemon + its mixins (added in the 2.1.0 monolith split)
    "daemon.py", "daemon_utils.py", "cli_parser.py",
    "logging_utils.py", "state_manager.py", "conky_manager.py",
    "playback_controller.py", "status_reports.py", "quran_data.py",
    # Rest of the app
    "quran_gui.py", "quran_search.py",
    "config_manager.py", "audio_player.py", "load.py",
    "version.py", "VERSION", "conky_config_manager.py", 
    "requirements.txt", "default_config.ini",
    "icon.png", "manual.txt", "quran-daemon.1",
]
APP_DIRS = ["quran-text", "audio"]
CONKY_FILES = ["conky_quran", "reshape_arabic.py", "display_verse.sh", "config.ini"]

# Amiri is bundled so a fresh install renders Arabic correctly even on
# minimal systems without fonts-hosny-amiri. install_font() copies it to
# ~/.local/share/fonts/ only if fontconfig doesn't already resolve "Amiri"
# from *any* source (distro package, previous install, etc.).
BUNDLED_FONT_FILE = "Amiri-Regular.ttf"
FONT_FAMILY = "Amiri"
FONT_INSTALL_MARKER = ".installed-fonts"

CLI_ENTRIES = [
    ("quran-daemon", "daemon.py", True),
    ("quran-gui", "quran_gui.py", False),
    ("quran-search", "quran_search.py", True),
]


def get_platform_paths() -> dict:
    home = Path.home()
    install_dir = home / ".quran-player"
    return {
        "install_dir": install_dir,
        "config_dir": home / ".config" / APP_NAME,
        "bin_dir": home / ".local" / "bin",
        "venv_dir": install_dir / "env",
        "python_exe": install_dir / "env" / "bin" / "python",
        "desktop_file": home / ".local" / "share" / "applications" / f"{APP_NAME}.desktop",
        "conky_dir": install_dir / "conky",
        "fonts_dir": home / ".local" / "share" / "fonts",
    }


# ---------------------------------------------------------------------------
# Version probes
# ---------------------------------------------------------------------------
def _python_version(exe) -> tuple:
    if not exe:
        return None
    try:
        r = subprocess.run(
            [str(exe), "-c", "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        return tuple(int(p) for p in r.stdout.strip().split("."))
    except Exception:
        return None


def _is_compatible(ver) -> bool:
    return bool(ver) and ver[:2] >= MIN_PYTHON


def _ver_str(ver) -> str:
    return ".".join(map(str, ver)) if ver else "unknown"


def get_base_python() -> str:
    candidates = [sys.executable]
    for minor in (13, 12, 11, 10, 9):
        for name in (f"python3.{minor}", f"python3.{minor}m"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    seen = set()
    for cand in candidates:
        real = os.path.realpath(cand)
        if real in seen:
            continue
        seen.add(real)
        if _is_compatible(_python_version(cand)):
            return cand
    return sys.executable


# ---------------------------------------------------------------------------
# Copy helpers
# ---------------------------------------------------------------------------
def needs_copy(src: Path, dest: Path) -> bool:
    if not dest.exists():
        return True
    if src.is_dir() != dest.is_dir():
        return True
    if src.is_file():
        if src.resolve() == dest.resolve():
            return False
        s, d = src.stat(), dest.stat()
        return s.st_size != d.st_size or s.st_mtime > d.st_mtime + 0.001
    return False


def copy_file_if_needed(src: Path, dest: Path, dry_run=False, verbose=False) -> bool:
    if not needs_copy(src, dest):
        if verbose:
            print(f"    = {dest}")
        return False
    if dry_run:
        print(f"    + {dest}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if verbose:
        print(f"    + {dest}")
    return True


def copy_tree_incremental(src_dir: Path, dest_dir: Path, dry_run=False, verbose=False,
                          remove_orphans=True):
    if not src_dir.is_dir():
        return 0, 0, []
    copied = skipped = 0
    src_files = set()
    for src in src_dir.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_dir)
        src_files.add(rel)
        if copy_file_if_needed(src, dest_dir / rel, dry_run, verbose):
            copied += 1
        else:
            skipped += 1
    removed = []
    if remove_orphans and dest_dir.exists():
        for dest in dest_dir.rglob("*"):
            if not dest.is_file():
                continue
            rel = dest.relative_to(dest_dir)
            if rel not in src_files:
                removed.append(rel)
                if dry_run:
                    print(f"    - {dest}")
                else:
                    dest.unlink()
    return copied, skipped, removed


# ---------------------------------------------------------------------------
# Venv + dependencies
# ---------------------------------------------------------------------------
def ensure_venv(paths: dict, dry_run=False) -> bool:
    venv_dir = paths["venv_dir"]
    if venv_dir.exists():
        return False
    python_exe = get_base_python()
    ver = _python_version(python_exe)
    if not _is_compatible(ver):
        print(f"    ✗ No compatible Python (need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
        print(f"       Best available: {python_exe} ({_ver_str(ver)})")
        return False
    if dry_run:
        print(f"    would create venv at {venv_dir} using {python_exe} ({_ver_str(ver)})")
        return True
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"    Creating venv at {venv_dir} (Python {_ver_str(ver)})...")
    subprocess.run([python_exe, "-m", "venv", str(venv_dir)], check=True)
    return True


def _requirements_hash(req: Path) -> str:
    return hashlib.sha256(req.read_bytes()).hexdigest() if req.exists() else ""


def ensure_dependencies(paths: dict, dry_run=False) -> bool:
    req = SOURCE_DIR / "requirements.txt"
    if not req.exists():
        print("    requirements.txt not found — skipping")
        return False
    hash_file = paths["install_dir"] / ".requirements.hash"
    new_hash = _requirements_hash(req)
    if hash_file.exists() and hash_file.read_text().strip() == new_hash:
        print("    Dependencies unchanged")
        return False
    if dry_run:
        print(f"    would install {req.name}")
        return True
    py = paths["python_exe"]
    subprocess.run([str(py), "-m", "pip", "uninstall", "-y", "pygame"],
                   check=False, capture_output=True)
    print("    Installing dependencies (pip)...")
    subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
                   check=True)
    subprocess.run([str(py), "-m", "pip", "install", "-r", str(req)], check=True)
    hash_file.write_text(new_hash)
    return True


def _verify_audio_stack(paths: dict) -> tuple:
    py = paths["python_exe"]
    if not py.exists():
        return False, "python missing"
    try:
        r = subprocess.run(
            [str(py), "-c", "import pygame; import pygame.mixer; print('ok')"],
            capture_output=True, text=True, timeout=20,
        )
        return (r.returncode == 0 and "ok" in r.stdout,
                (r.stderr or r.stdout).strip() if r.returncode != 0 else "")
    except Exception as e:
        return False, str(e)


def _verify_conky_deps(paths: dict) -> tuple:
    py = paths["python_exe"]
    if not py.exists():
        return False, "python missing"
    try:
        r = subprocess.run(
            [str(py), "-c", "import arabic_reshaper, bidi; print('ok')"],
            capture_output=True, text=True, timeout=10,
        )
        return (r.returncode == 0 and "ok" in r.stdout,
                (r.stderr or r.stdout).strip() if r.returncode != 0 else "")
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Conky widget
# ---------------------------------------------------------------------------
def install_conky(paths: dict, dry_run=False):
    src_dir = SOURCE_DIR / "quran_daemon_conky"
    if not src_dir.is_dir():
        print("    quran_daemon_conky/ not found — skipping")
        return

    dst_dir = paths["conky_dir"]
    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)

    for fname in CONKY_FILES:
        src = src_dir / fname
        if not src.exists():
            print(f"    ⚠  Missing: {src.name}")
            continue
        copy_file_if_needed(src, dst_dir / fname, dry_run)

    # Sweep orphans: conky/ is entirely installer-managed, so any file not
    # in CONKY_FILES is obsolete (e.g. reshape_arabic.sh from pre-2.1).
    if dst_dir.exists():
        allowed = set(CONKY_FILES) | {"__pycache__"}
        for entry in dst_dir.iterdir():
            if entry.name in allowed or entry.is_dir():
                continue
            if dry_run:
                print(f"    - {entry} (orphan)")
            else:
                print(f"    - {entry} (orphan, removed)")
                try:
                    entry.unlink()
                except OSError as e:
                    print(f"      failed: {e}")

    sh = dst_dir / "display_verse.sh"
    if not dry_run and sh.exists():
        os.chmod(sh, 0o755)

    if not dry_run and shutil.which("conky") is None:
        print("    ⚠  conky not installed — install with: sudo apt install conky-all")
        print("       (verse display will stay off until conky is installed)")

    print(f"    Conky widget: {dst_dir}")


# ---------------------------------------------------------------------------
# Amiri font (bundled fallback)
# ---------------------------------------------------------------------------
def _fc_match_amiri() -> bool:
    """True if fontconfig already resolves 'Amiri' from *any* source.

    Uses fc-match --format to get the resolved family name; if fc-match is
    not installed (very rare — ships with fontconfig), assume Amiri is
    present rather than shadow a user-installed font.
    """
    if shutil.which("fc-match") is None:
        return True
    try:
        r = subprocess.run(
            ["fc-match", FONT_FAMILY, "--format=%{family}\n"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return True
        resolved = r.stdout.strip().split(",")[0].strip()
        return resolved.lower() == FONT_FAMILY.lower()
    except Exception:
        return True


def install_font(paths: dict, dry_run=False):
    """Copy bundled Amiri into ~/.local/share/fonts if not already present.

    Records destinations in install_dir/.installed-fonts so uninstall can
    remove exactly what we added (never touching user-installed fonts).
    """
    src = SOURCE_DIR / "quran_daemon_conky" / BUNDLED_FONT_FILE
    if not src.exists():
        print(f"    ⚠  Font bundle missing: {src.name} — conky may fall back")
        return

    if _fc_match_amiri():
        print(f"    fontconfig already resolves '{FONT_FAMILY}' — skipping")
        return

    dest = paths["fonts_dir"] / BUNDLED_FONT_FILE
    if dry_run:
        print(f"    would install {dest}")
        return

    paths["fonts_dir"].mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    # Refresh fontconfig cache so conky sees the font on next launch.
    if shutil.which("fc-cache"):
        subprocess.run(
            ["fc-cache", "-f", str(paths["fonts_dir"])],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    marker = paths["install_dir"] / FONT_INSTALL_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    with open(marker, "a", encoding="utf-8") as f:
        f.write(str(dest) + "\n")

    print(f"    Installed {BUNDLED_FONT_FILE} → {dest}")


def remove_installed_fonts(paths: dict, dry_run=False):
    """Remove only fonts the installer added, based on .installed-fonts."""
    marker = paths["install_dir"] / FONT_INSTALL_MARKER
    if not marker.exists():
        return
    try:
        lines = [l.strip() for l in marker.read_text().splitlines() if l.strip()]
    except OSError:
        return
    for raw in lines:
        path = Path(raw)
        if dry_run:
            print(f"    would remove font {path}")
            continue
        if path.exists():
            try:
                path.unlink()
                print(f"    removed font {path}")
                if shutil.which("fc-cache"):
                    subprocess.run(
                        ["fc-cache", "-f", str(path.parent)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
            except OSError as e:
                print(f"      failed to remove {path}: {e}")


def _font_status(paths: dict) -> str:
    """Human-readable Amiri status for the summary."""
    marker = paths["install_dir"] / FONT_INSTALL_MARKER
    font_path = paths["fonts_dir"] / BUNDLED_FONT_FILE
    if marker.exists() and font_path.exists():
        return f"bundled → {font_path}"
    if _fc_match_amiri():
        return "system (fc-match resolved)"
    return "⚠ not installed — conky will use a fallback font"


# ---------------------------------------------------------------------------
# CLI wrappers
# ---------------------------------------------------------------------------
def create_wrappers(paths: dict, dry_run=False) -> int:
    bin_dir = paths["bin_dir"]
    created = 0
    for name, script, needs_console in CLI_ENTRIES:
        script_path = paths["install_dir"] / script
        wrapper = bin_dir / name

        if needs_console:
            content = (
                "#!/bin/bash\n"
                f'exec "{paths["python_exe"]}" "{script_path}" "$@"\n'
            )
        else:
            # GUI: detach from terminal unless --foreground / -f is passed.
            # setsid -f re-runs us in a new session so closing the terminal
            # (SIGHUP to the process group) can't kill the GUI.
            content = (
                "#!/bin/bash\n"
                f'PY="{paths["python_exe"]}"\n'
                f'SCRIPT="{script_path}"\n'
                'if [ "$1" = "--foreground" ] || [ "$1" = "-f" ]; then\n'
                '    shift\n'
                '    exec "$PY" "$SCRIPT" "$@"\n'
                'fi\n'
                'if [ -t 0 ] || [ -t 1 ]; then\n'
                '    setsid -f "$PY" "$SCRIPT" "$@" </dev/null >/dev/null 2>&1\n'
                '    exit 0\n'
                'fi\n'
                'exec "$PY" "$SCRIPT" "$@"\n'
            )

        if dry_run:
            print(f"    would write {wrapper}")
            created += 1
            continue
        bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(content, encoding="utf-8")
        os.chmod(wrapper, 0o755)
        created += 1
    return created


def remove_wrappers(paths: dict, dry_run=False):
    for name, _, _ in CLI_ENTRIES:
        p = paths["bin_dir"] / name
        if p.exists() or p.is_symlink():
            if dry_run:
                print(f"    would remove {p}")
            else:
                try:
                    p.unlink()
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Desktop entry
# ---------------------------------------------------------------------------
def create_desktop_shortcut(paths: dict, dry_run=False):
    desktop_file = paths["desktop_file"]
    content = (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Name=Quran Player\n"
        "Comment=Quran Player with Conky verse display\n"
        f"Exec={paths['bin_dir'] / 'quran-gui'}\n"
        f"Icon={paths['install_dir'] / 'icon.png'}\n"
        "Terminal=false\n"
        "Type=Application\n"
        "Categories=Audio;Education;\n"
    )
    if dry_run:
        print(f"    would write {desktop_file}")
        return
    desktop_file.parent.mkdir(parents=True, exist_ok=True)
    desktop_file.write_text(content, encoding="utf-8")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(desktop_file.parent)],
                       capture_output=True)


def remove_desktop_shortcut(paths: dict, dry_run=False):
    p = paths["desktop_file"]
    if p.exists():
        if dry_run:
            print(f"    would remove {p}")
        else:
            try:
                p.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# App copy
# ---------------------------------------------------------------------------
def copy_app_files(paths: dict, dry_run=False, verbose=False):
    dest_root = paths["install_dir"]
    if not dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)
    total_copied = total_skipped = 0
    removed = []
    for fname in APP_FILES:
        src = SOURCE_DIR / fname
        if not src.exists():
            continue
        if copy_file_if_needed(src, dest_root / fname, dry_run, verbose):
            total_copied += 1
        else:
            total_skipped += 1
    for dname in APP_DIRS:
        src_dir = SOURCE_DIR / dname
        if not src_dir.is_dir():
            continue
        c, s, r = copy_tree_incremental(
            src_dir, dest_root / dname, dry_run, verbose,
            remove_orphans=(dname == "quran-text"),
        )
        total_copied += c
        total_skipped += s
        removed.extend(r)
    return total_copied, total_skipped, removed


# ---------------------------------------------------------------------------
# Daemon control
# ---------------------------------------------------------------------------
def stop_daemon_if_running(paths: dict):
    wrapper = paths["bin_dir"] / "quran-daemon"
    if wrapper.exists():
        try:
            subprocess.run([str(wrapper), "stop"], timeout=5, capture_output=True)
        except Exception:
            pass
    pid_file = paths["install_dir"] / "control" / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 15)
            import time
            time.sleep(0.5)
        except (ValueError, OSError):
            pass


# ---------------------------------------------------------------------------
# Wipe
# ---------------------------------------------------------------------------
def wipe_install(paths: dict, dry_run=False, keep_config=True):
    if dry_run:
        print("    would stop daemon")
        print(f"    would remove {paths['install_dir']}")
        remove_installed_fonts(paths, dry_run=True)
    else:
        stop_daemon_if_running(paths)
        # Fonts live outside install_dir, so remove them before rmtree
        # destroys the marker file that tracks what we installed.
        remove_installed_fonts(paths, dry_run=False)
        shutil.rmtree(paths["install_dir"], ignore_errors=True)
    remove_wrappers(paths, dry_run)
    remove_desktop_shortcut(paths, dry_run)
    if not keep_config:
        if dry_run:
            print(f"    would remove {paths['config_dir']}")
        else:
            shutil.rmtree(paths["config_dir"], ignore_errors=True)


# ---------------------------------------------------------------------------
# PATH shadowing warning
# ---------------------------------------------------------------------------
def _warn_about_shadowing(paths: dict):
    issues = []
    for cmd in ("quran-daemon", "quran-gui", "quran-search"):
        resolved = shutil.which(cmd)
        if not resolved:
            continue
        try:
            same = Path(resolved).resolve() == (paths["bin_dir"] / cmd).resolve()
        except OSError:
            same = False
        if not same:
            issues.append((cmd, resolved))
    if not issues:
        return
    print()
    print("  ⚠  PATH shadowing detected:")
    for cmd, resolved in issues:
        print(f"       {cmd} → {resolved}")
    print()
    print("     Check with: type quran-daemon")
    print(f"     Fix: ensure {paths['bin_dir']} is early in PATH, remove stale aliases.")
    print()


# ---------------------------------------------------------------------------
# Install orchestration
# ---------------------------------------------------------------------------
def install(paths: dict, clean=False, dry_run=False, verbose=False, with_conky=True):
    if clean:
        print("[0/7] --clean: wiping existing installation (config preserved)")
        wipe_install(paths, dry_run=dry_run, keep_config=True)

    print("[1/7] Copying application files")
    copied, skipped, removed = copy_app_files(paths, dry_run, verbose)
    print(f"      {copied} copied, {skipped} unchanged, {len(removed)} removed")

    print("[2/7] Installing Conky widget" if with_conky else "[2/7] Conky widget: skipped")
    if with_conky:
        install_conky(paths, dry_run)
        install_font(paths, dry_run)

    print("[3/7] Ensuring virtual environment")
    created = ensure_venv(paths, dry_run)
    print("      created" if created else "      already present")

    print("[4/7] Checking dependencies")
    print("      installed / updated" if ensure_dependencies(paths, dry_run) else "      up to date")

    print("[5/7] Verifying runtime deps")
    if dry_run:
        print("      (skipped in dry-run)")
    else:
        ok, err = _verify_audio_stack(paths)
        if not ok:
            print("      ✗ pygame.mixer cannot be imported")
            print(f"        stderr: {err.splitlines()[0] if err else '?'}")
            print("        Fix: pip install --force-reinstall pygame-ce")
            sys.exit(1)
        if with_conky:
            ok, err = _verify_conky_deps(paths)
            if not ok:
                print("      ✗ conky deps (arabic-reshaper/bidi) missing")
                print(f"        stderr: {err.splitlines()[0] if err else '?'}")
                sys.exit(1)
        print("      OK")

    print("[6/7] Creating CLI wrappers")
    print(f"      {create_wrappers(paths, dry_run)} wrappers")

    print("[7/7] Creating desktop shortcut")
    create_desktop_shortcut(paths, dry_run)
    print(f"      {paths['desktop_file']}")

    print()
    print_summary(paths, with_conky)
    if not dry_run:
        _warn_about_shadowing(paths)


def print_summary(paths: dict, with_conky: bool):
    print("=" * 70)
    print("  ✓ quran-player installed (Linux)")
    print("=" * 70)
    print(f"  Install dir : {paths['install_dir']}")
    print(f"  Config dir  : {paths['config_dir']}")
    print(f"  Wrappers    : {paths['bin_dir']}")
    if with_conky:
        print(f"  Conky dir   : {paths['conky_dir']}")
        print(f"  Amiri font  : {_font_status(paths)}")
    print()
    print("  Try it:")
    print("    quran-daemon start &")
    print("    quran-daemon play")
    print("    quran-daemon conky_off   # hide desktop verse")
    print("    quran-daemon conky_on    # show it again")
    print()
    if str(paths["bin_dir"]) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f"  ⚠  Add to ~/.bashrc:")
        print(f'      export PATH="{paths["bin_dir"]}:$PATH"')
        print()
    if with_conky and shutil.which("conky") is None:
        print("  ⚠  Install conky to see the verse on your desktop:")
        print("      sudo apt install conky-all       # Debian/Ubuntu")
        print("      sudo pacman -S conky             # Arch")
        print("      sudo dnf install conky           # Fedora")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Linux-native installer for quran-player (no root required).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python install.py                   # install / update\n"
            "  python install.py --clean           # wipe install (keep config), reinstall\n"
            "  python install.py --uninstall       # remove install, keep config\n"
            "  python install.py --uninstall --purge\n"
        ),
    )
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--no-conky", action="store_true",
                        help="skip Conky widget installation")

    args = parser.parse_args()

    if os.geteuid() == 0:
        print("⚠  Running as root — files will go to /root/.quran-player.")
        import time
        time.sleep(3)

    if not SOURCE_DIR.joinpath("daemon.py").exists():
        print("Error: install.py must be run from the quran-player source directory")
        sys.exit(1)

    paths = get_platform_paths()

    if args.uninstall:
        print(f"Uninstalling quran-player from {paths['install_dir']}")
        wipe_install(paths, dry_run=args.dry_run, keep_config=not args.purge)
        print("✓ Uninstall complete." if not args.dry_run else "✓ Dry-run: no changes made.")
        return

    install(paths, clean=args.clean, dry_run=args.dry_run,
            verbose=args.verbose, with_conky=not args.no_conky)

    if args.dry_run:
        print("✓ Dry-run: no changes made.")


if __name__ == "__main__":
    main()
    