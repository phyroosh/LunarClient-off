import os
import shutil
import zipfile
import tarfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"

if DIST.exists():
    shutil.rmtree(DIST)
DIST.mkdir(parents=True, exist_ok=True)

VERSION = "1.0.0"

# 1. Windows Package (.zip)
win_dir = DIST / f"LunarClient-Offline-v{VERSION}-Windows"
win_dir.mkdir()
shutil.copy2(ROOT / "LunarOffline.bat", win_dir / "LunarOffline.bat")
shutil.copy2(ROOT / "FixLunarOffline.bat", win_dir / "FixLunarOffline.bat")
shutil.copy2(ROOT / "lunar_offline_manager.py", win_dir / "lunar_offline_manager.py")
shutil.copy2(ROOT / "icon.png", win_dir / "icon.png")
shutil.copy2(ROOT / "README.md", win_dir / "README.md")
shutil.copy2(ROOT / "LICENSE", win_dir / "LICENSE")

scripts_dir = win_dir / "scripts"
scripts_dir.mkdir()
shutil.copy2(ROOT / "scripts" / "lunar_offline_gui.ps1", scripts_dir / "lunar_offline_gui.ps1")

win_zip_path = DIST / f"LunarClient-Offline-v{VERSION}-Windows.zip"
with zipfile.ZipFile(win_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(win_dir):
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(win_dir)
            zf.write(full_p, arcname=str(rel_p))
shutil.rmtree(win_dir)
print(f"[✓] Built {win_zip_path.name} ({win_zip_path.stat().st_size / 1024:.1f} KB)")


# Helper for Linux packages
def make_linux_pkg(pkg_name, extra_files=None):
    pkg_dir = DIST / pkg_name
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir()

    shutil.copy2(ROOT / "install.sh", pkg_dir / "install.sh")
    shutil.copy2(ROOT / "uninstall.sh", pkg_dir / "uninstall.sh")
    shutil.copy2(ROOT / "lunar_offline_manager.py", pkg_dir / "lunar_offline_manager.py")
    shutil.copy2(ROOT / "icon.png", pkg_dir / "icon.png")
    shutil.copy2(ROOT / "README.md", pkg_dir / "README.md")
    shutil.copy2(ROOT / "LICENSE", pkg_dir / "LICENSE")

    os.chmod(pkg_dir / "install.sh", 0o755)
    os.chmod(pkg_dir / "uninstall.sh", 0o755)
    os.chmod(pkg_dir / "lunar_offline_manager.py", 0o755)

    if extra_files:
        for fname, content in extra_files.items():
            fpath = pkg_dir / fname
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(fpath, 0o755)

    # Make .tar.gz
    tar_path = DIST / f"{pkg_name}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(pkg_dir, arcname=pkg_name)
    print(f"[✓] Built {tar_path.name} ({tar_path.stat().st_size / 1024:.1f} KB)")

    # Make .zip
    zip_path = DIST / f"{pkg_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(pkg_dir):
            for f in files:
                full_p = Path(root) / f
                rel_p = full_p.relative_to(DIST)
                zf.write(full_p, arcname=str(rel_p))
    print(f"[✓] Built {zip_path.name} ({zip_path.stat().st_size / 1024:.1f} KB)")

    shutil.rmtree(pkg_dir)


# 2. Universal Linux Package
make_linux_pkg(f"LunarClient-Offline-v{VERSION}-Linux-Universal")

# 3. Fedora & RHEL Package
fedora_script = """#!/usr/bin/env bash
set -e
echo "========================================================="
echo "  🌙 Lunar Client Offline Setup for Fedora / RHEL"
echo "========================================================="
echo "[*] Installing required packages via dnf..."
sudo dnf install -y python3 python3-tkinter squashfs-tools fuse-libs
echo "[*] Running installation..."
./install.sh
"""
make_linux_pkg(f"LunarClient-Offline-v{VERSION}-Fedora-RHEL", {"setup-fedora.sh": fedora_script})

# 4. Ubuntu, Debian & Mint Package
ubuntu_script = """#!/usr/bin/env bash
set -e
echo "========================================================="
echo "  🌙 Lunar Client Offline Setup for Ubuntu / Debian / Mint"
echo "========================================================="
echo "[*] Installing required packages via apt..."
sudo apt-get update
sudo apt-get install -y python3 python3-tk squashfs-tools libfuse2 2>/dev/null || sudo apt-get install -y python3 python3-tk squashfs-tools libfuse2t64
echo "[*] Running installation..."
./install.sh
"""
make_linux_pkg(f"LunarClient-Offline-v{VERSION}-Ubuntu-Debian-Mint", {"setup-ubuntu-mint.sh": ubuntu_script})

# 5. Arch Linux & Manjaro Package
arch_script = """#!/usr/bin/env bash
set -e
echo "========================================================="
echo "  🌙 Lunar Client Offline Setup for Arch Linux / Manjaro"
echo "========================================================="
echo "[*] Installing required packages via pacman..."
sudo pacman -S --needed --noconfirm python tk squashfs-tools fuse2
echo "[*] Running installation..."
./install.sh
"""
make_linux_pkg(f"LunarClient-Offline-v{VERSION}-Arch-Manjaro", {"setup-arch.sh": arch_script})

print("\n[✓] All release archives generated successfully in dist/!")
