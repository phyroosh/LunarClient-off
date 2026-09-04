#!/usr/bin/env bash
# ==============================================================================
# Lunar Client Offline Manager - Universal Linux Installer
# Supports: Arch, Fedora, Ubuntu, Linux Mint, Debian, openSUSE, Alpine, Void, etc.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/512x512/apps"
PIXMAPS_DIR="${HOME}/.local/share/pixmaps"

echo "========================================================"
echo "    🌙 Lunar Client Offline Manager - Linux Installer"
echo "========================================================"

# Detect Distribution
DISTRO_ID="unknown"
DISTRO_LIKE=""
DISTRO_NAME="Linux"
if [ -f /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
    DISTRO_LIKE="${ID_LIKE:-}"
    DISTRO_NAME="${NAME:-${PRETTY_NAME:-Linux}}"
fi

echo "[*] Detected System: ${DISTRO_NAME} (${DISTRO_ID})"
echo

# ------------------------------------------------------------------------------
# 1. Dependency Checks & Automated Installation
# ------------------------------------------------------------------------------
NEED_PYTHON=0
NEED_TK=0
NEED_SQUASHFS=0
NEED_FUSE=0

if ! command -v python3 &>/dev/null; then
    NEED_PYTHON=1
fi

if ! python3 -c "import tkinter" &>/dev/null; then
    NEED_TK=1
fi

if ! command -v unsquashfs &>/dev/null || ! command -v mksquashfs &>/dev/null; then
    NEED_SQUASHFS=1
fi

# AppImages require FUSE 2 runtime library (libfuse.so.2)
check_fuse2() {
    if ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2'; then
        return 0
    fi
    for f in /lib/x86_64-linux-gnu/libfuse.so.2* /usr/lib/x86_64-linux-gnu/libfuse.so.2* /usr/lib64/libfuse.so.2* /usr/lib/libfuse.so.2*; do
        if [ -e "$f" ]; then
            return 0
        fi
    done
    return 1
}

if ! check_fuse2; then
    NEED_FUSE=1
fi

PKGS_TO_INSTALL=()
INSTALL_CMD=""

if [ "$NEED_PYTHON" -eq 1 ] || [ "$NEED_TK" -eq 1 ] || [ "$NEED_SQUASHFS" -eq 1 ] || [ "$NEED_FUSE" -eq 1 ]; then
    echo "[*] Resolving missing dependencies..."

    # Arch Linux / Manjaro / EndeavourOS / Garuda
    if command -v pacman &>/dev/null; then
        INSTALL_CMD="sudo pacman -S --needed --noconfirm"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("tk")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs-tools")
        [ "$NEED_FUSE" -eq 1 ] && PKGS_TO_INSTALL+=("fuse2")

    # Fedora / RHEL / Rocky / AlmaLinux / CentOS
    elif command -v dnf &>/dev/null; then
        INSTALL_CMD="sudo dnf install -y"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python3")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("python3-tkinter")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs-tools")
        [ "$NEED_FUSE" -eq 1 ] && PKGS_TO_INSTALL+=("fuse-libs")

    # Ubuntu / Debian / Linux Mint / Pop!_OS / Elementary / Zorin
    elif command -v apt-get &>/dev/null; then
        INSTALL_CMD="sudo apt-get update && sudo apt-get install -y"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python3")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("python3-tk")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs-tools")
        if [ "$NEED_FUSE" -eq 1 ]; then
            # Ubuntu 24.04+ (noble) transitioned to libfuse2t64
            if apt-cache show libfuse2t64 &>/dev/null; then
                PKGS_TO_INSTALL+=("libfuse2t64")
            else
                PKGS_TO_INSTALL+=("libfuse2")
            fi
        fi

    # openSUSE
    elif command -v zypper &>/dev/null; then
        INSTALL_CMD="sudo zypper install -y"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python3")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("python3-tk")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs")
        [ "$NEED_FUSE" -eq 1 ] && PKGS_TO_INSTALL+=("fuse")

    # Alpine Linux
    elif command -v apk &>/dev/null; then
        INSTALL_CMD="sudo apk add"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python3")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("py3-tkinter")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs-tools")
        [ "$NEED_FUSE" -eq 1 ] && PKGS_TO_INSTALL+=("fuse")

    # Void Linux
    elif command -v xbps-install &>/dev/null; then
        INSTALL_CMD="sudo xbps-install -y"
        [ "$NEED_PYTHON" -eq 1 ] && PKGS_TO_INSTALL+=("python3")
        [ "$NEED_TK" -eq 1 ] && PKGS_TO_INSTALL+=("python3-tkinter")
        [ "$NEED_SQUASHFS" -eq 1 ] && PKGS_TO_INSTALL+=("squashfs-tools")
        [ "$NEED_FUSE" -eq 1 ] && PKGS_TO_INSTALL+=("fuse")

    else
        echo "[!] Warning: Unknown package manager."
        echo "    Please manually install: python3, tkinter, squashfs-tools, and libfuse2"
    fi

    if [ ${#PKGS_TO_INSTALL[@]} -gt 0 ] && [ -n "$INSTALL_CMD" ]; then
        echo "[*] Installing required packages: ${PKGS_TO_INSTALL[*]}"
        eval "${INSTALL_CMD} ${PKGS_TO_INSTALL[*]}"
    fi
else
    echo "[✓] All prerequisites satisfied (Python 3, Tkinter, squashfs-tools, FUSE)."
fi

echo

# ------------------------------------------------------------------------------
# 2. Target Directories & File Permissions
# ------------------------------------------------------------------------------
mkdir -p "${BIN_DIR}"
mkdir -p "${APPS_DIR}"
mkdir -p "${ICON_DIR}"
mkdir -p "${PIXMAPS_DIR}"

chmod +x "${SCRIPT_DIR}/lunar_offline_manager.py"

# ------------------------------------------------------------------------------
# 3. Install Wrapper into ~/.local/bin/lunar-offline
# ------------------------------------------------------------------------------
cat << WRAPPER > "${BIN_DIR}/lunar-offline"
#!/usr/bin/env bash
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
TARGET=""
CANDIDATES=(
    "${SCRIPT_DIR}/lunar_offline_manager.py"
    "\${HOME}/.local/share/lunar-offline/lunar_offline_manager.py"
)
for c in "\${CANDIDATES[@]}"; do
    if [ -f "\$c" ]; then
        TARGET="\$c"
        break
    fi
done

if [ -z "\$TARGET" ]; then
    echo "[!] Error: lunar_offline_manager.py not found at ${SCRIPT_DIR}/lunar_offline_manager.py"
    exit 1
fi

exec python3 "\$TARGET" "\$@"
WRAPPER
chmod +x "${BIN_DIR}/lunar-offline"

# ------------------------------------------------------------------------------
# 4. Icon & Desktop Entry Setup
# ------------------------------------------------------------------------------
if [ -f "${SCRIPT_DIR}/icon.png" ]; then
    cp -f "${SCRIPT_DIR}/icon.png" "${ICON_DIR}/lunar-offline.png"
    cp -f "${SCRIPT_DIR}/icon.png" "${ICON_DIR}/lunarclient.png"
    cp -f "${SCRIPT_DIR}/icon.png" "${PIXMAPS_DIR}/lunar-offline.png"
    cp -f "${SCRIPT_DIR}/icon.png" "${PIXMAPS_DIR}/lunarclient.png"
fi

cat << DESKTOP > "${APPS_DIR}/lunar-offline.desktop"
[Desktop Entry]
Name=Lunar Client Offline Manager
GenericName=Minecraft Offline Account Manager
Comment=Manage offline Minecraft accounts and skins for Lunar Client
Exec=${BIN_DIR}/lunar-offline gui
Icon=lunar-offline
Terminal=false
Type=Application
Categories=Game;Utility;
Keywords=minecraft;lunar;offline;skin;
StartupNotify=true
DESKTOP
chmod +x "${APPS_DIR}/lunar-offline.desktop"

# Refresh desktop & icon databases across DEs
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v kbuildsycoca6 &>/dev/null; then
    kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 &>/dev/null; then
    kbuildsycoca5 --noincremental 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# 5. Shell PATH Configuration
# ------------------------------------------------------------------------------
configure_shell_path() {
    local rc_file="$1"
    if [ -f "$rc_file" ]; then
        if ! grep -q 'export PATH=.*\.local/bin' "$rc_file" 2>/dev/null; then
            echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "$rc_file"
            echo "[*] Added ~/.local/bin to PATH in ${rc_file}"
        fi
    fi
}

if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    configure_shell_path "${HOME}/.bashrc"
    configure_shell_path "${HOME}/.zshrc"
    configure_shell_path "${HOME}/.profile"
    
    # Fish shell support
    if [ -d "${HOME}/.config/fish" ]; then
        FISH_CONF="${HOME}/.config/fish/config.fish"
        mkdir -p "${HOME}/.config/fish"
        if [ ! -f "$FISH_CONF" ] || ! grep -q '\.local/bin' "$FISH_CONF" 2>/dev/null; then
            echo 'fish_add_path -a $HOME/.local/bin' >> "$FISH_CONF"
            echo "[*] Added ~/.local/bin to PATH in ${FISH_CONF}"
        fi
    fi
fi

echo "[✓] Lunar Client Offline Manager installed successfully!"
echo "    - Terminal Command: lunar-offline"
echo "    - CLI Menu:         lunar-offline menu"
echo "    - Graphical GUI:    lunar-offline gui (or launch from Application Menu)"
echo

# ------------------------------------------------------------------------------
# 6. Locate Lunar Client AppImage & Offer to Patch
# ------------------------------------------------------------------------------
LUNAR_APPIMAGE=""
CANDIDATES=(
    "${HOME}/Lunar client/Lunar_Client.AppImage"
    "${HOME}/LunarClient/Lunar_Client.AppImage"
    "${HOME}/Applications/Lunar_Client.AppImage"
    "${HOME}/Downloads/Lunar_Client.AppImage"
    "${HOME}/Desktop/Lunar_Client.AppImage"
    "${HOME}/.local/bin/Lunar_Client.AppImage"
    "/usr/local/bin/Lunar_Client.AppImage"
    "/opt/Lunar Client/Lunar_Client.AppImage"
    "/opt/lunarclient/Lunar_Client.AppImage"
    "$(pwd)/Lunar_Client.AppImage"
)

for c in "${CANDIDATES[@]}"; do
    if [ -f "$c" ]; then
        LUNAR_APPIMAGE="$c"
        break
    fi
done

# Fallback: scan for any case-insensitive *lunar*.AppImage in common folders
if [ -z "$LUNAR_APPIMAGE" ]; then
    for dir in "${HOME}/Applications" "${HOME}/Downloads" "${HOME}/Desktop" "${HOME}/Lunar client"; do
        if [ -d "$dir" ]; then
            matched=$(find "$dir" -maxdepth 2 -type f -iname "*lunar*.appimage" 2>/dev/null | head -n 1)
            if [ -n "$matched" ]; then
                LUNAR_APPIMAGE="$matched"
                break
            fi
        fi
    done
fi

if [ -n "$LUNAR_APPIMAGE" ]; then
    echo "[*] Found Lunar Client AppImage at: ${LUNAR_APPIMAGE}"

    # Fix unquoted spaces in official lunar-client.desktop if present
    LUNAR_DESKTOP="${APPS_DIR}/lunar-client.desktop"
    if [ -f "$LUNAR_DESKTOP" ]; then
        if grep -q 'Exec=[^"].* [^"].*' "$LUNAR_DESKTOP" 2>/dev/null; then
            sed -i "s|Exec=.*|Exec=\"${LUNAR_APPIMAGE}\" %U|" "$LUNAR_DESKTOP"
            echo "[*] Fixed unquoted path with spaces in ${LUNAR_DESKTOP}"
        fi
    fi

    # If icon was extracted from AppImage
    if [ ! -f "${ICON_DIR}/lunar-offline.png" ]; then
        "${LUNAR_APPIMAGE}" --appimage-extract "usr/share/icons/hicolor/1024x1024/apps/lunarclient.png" &>/dev/null || true
        if [ -f "squashfs-root/usr/share/icons/hicolor/1024x1024/apps/lunarclient.png" ]; then
            cp -f "squashfs-root/usr/share/icons/hicolor/1024x1024/apps/lunarclient.png" "${ICON_DIR}/lunar-offline.png"
            cp -f "squashfs-root/usr/share/icons/hicolor/1024x1024/apps/lunarclient.png" "${PIXMAPS_DIR}/lunar-offline.png"
            rm -rf squashfs-root
        fi
    fi

    read -p "Would you like to apply the offline patch to it now? (Y/n): " DO_PATCH
    DO_PATCH=${DO_PATCH:-Y}
    if [[ "$DO_PATCH" =~ ^[Yy]$ ]]; then
        "${BIN_DIR}/lunar-offline" patch --appimage "${LUNAR_APPIMAGE}"
    fi
else
    echo "[!] Lunar Client AppImage was not automatically found."
    echo "    Download it from https://www.lunarclient.com/download/ and run:"
    echo "    lunar-offline patch --appimage /path/to/Lunar_Client.AppImage"
fi

echo
echo "========================================================"
echo "  Installation Complete! 🚀"
echo "  Run 'lunar-offline' to start managing your accounts."
echo "========================================================"
