#!/usr/bin/env bash
# ==============================================================================
# Lunar Client Offline Manager - 1-Click Installer
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"

echo "========================================================"
echo "      Lunar Client Offline Manager - Installer"
echo "========================================================"
echo

# 1. Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "[!] Error: python3 is required but was not found."
    echo "    Please install Python 3 (e.g. sudo dnf install -y python3)"
    exit 1
fi

# 2. Check squashfs-tools (unsquashfs & mksquashfs)
MISSING_TOOLS=0
if ! command -v unsquashfs &>/dev/null; then
    MISSING_TOOLS=1
fi
if ! command -v mksquashfs &>/dev/null; then
    MISSING_TOOLS=1
fi

if [ "$MISSING_TOOLS" -eq 1 ]; then
    echo "[*] squashfs-tools is required to patch AppImages."
    if command -v dnf &>/dev/null; then
        echo "    Installing squashfs-tools via dnf..."
        sudo dnf install -y squashfs-tools
    elif command -v apt-get &>/dev/null; then
        echo "    Installing squashfs-tools via apt..."
        sudo apt-get update && sudo apt-get install -y squashfs-tools
    elif command -v pacman &>/dev/null; then
        echo "    Installing squashfs-tools via pacman..."
        sudo pacman -S --noconfirm squashfs-tools
    else
        echo "[!] Please install 'squashfs-tools' using your package manager."
        exit 1
    fi
fi

# 3. Ensure target directories exist
mkdir -p "${BIN_DIR}"
mkdir -p "${APPS_DIR}"

# 4. Make python script executable
chmod +x "${SCRIPT_DIR}/lunar_offline_manager.py"

# 5. Install launcher wrapper to ~/.local/bin/lunar-offline
cat << WRAPPER > "${BIN_DIR}/lunar-offline"
#!/usr/bin/env bash
exec python3 "${SCRIPT_DIR}/lunar_offline_manager.py" "\$@"
WRAPPER
chmod +x "${BIN_DIR}/lunar-offline"

# 6. Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${BIN_DIR}:"* ]]; then
    SHELL_RC="${HOME}/.bashrc"
    if [ -n "$ZSH_VERSION" ] || [ -f "${HOME}/.zshrc" ]; then
        SHELL_RC="${HOME}/.zshrc"
    fi
    if ! grep -q 'export PATH=.*\.local/bin' "${SHELL_RC}" 2>/dev/null; then
        echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "${SHELL_RC}"
        echo "[*] Added ${BIN_DIR} to PATH in ${SHELL_RC}."
    fi
fi

# 7. Install Desktop Entry
cat << DESKTOP > "${APPS_DIR}/lunar-offline.desktop"
[Desktop Entry]
Name=Lunar Client Offline Manager
Comment=Manage offline Minecraft accounts and skins for Lunar Client
Exec=${BIN_DIR}/lunar-offline gui
Icon=lunarclient
Terminal=false
Type=Application
Categories=Game;Utility;
Keywords=minecraft;lunar;offline;skin;
DESKTOP
chmod +x "${APPS_DIR}/lunar-offline.desktop"

# Try to update desktop database if tool exists
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${APPS_DIR}" 2>/dev/null || true
fi

echo "[✓] Lunar Client Offline Manager installed successfully!"
echo "    - Command: lunar-offline"
echo "    - Desktop app: Available in your Application Menu"
echo

# 8. Check for Lunar Client AppImage and offer to patch
LUNAR_APPIMAGE=""
CANDIDATES=(
    "${HOME}/Lunar client/Lunar_Client.AppImage"
    "${HOME}/Downloads/Lunar_Client.AppImage"
    "${HOME}/Applications/Lunar_Client.AppImage"
    "${HOME}/.local/bin/Lunar_Client.AppImage"
)

for c in "${CANDIDATES[@]}"; do
    if [ -f "$c" ]; then
        LUNAR_APPIMAGE="$c"
        break
    fi
done

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
echo "All set! You can now launch Lunar Client Offline Manager with: lunar-offline"
