#!/usr/bin/env bash
# ==============================================================================
# Lunar Client Offline Manager - Uninstaller
# ==============================================================================
set -e

BIN_FILE="${HOME}/.local/bin/lunar-offline"
DESKTOP_FILE="${HOME}/.local/share/applications/lunar-offline.desktop"
ICON_FILE="${HOME}/.local/share/icons/hicolor/512x512/apps/lunar-offline.png"
PIXMAP_FILE="${HOME}/.local/share/pixmaps/lunar-offline.png"

echo "========================================================"
echo "    🌙 Lunar Client Offline Manager - Uninstaller"
echo "========================================================"
echo

if [ -f "${BIN_FILE}" ]; then
    rm -f "${BIN_FILE}"
    echo "[✓] Removed ${BIN_FILE}"
fi

if [ -f "${DESKTOP_FILE}" ]; then
    rm -f "${DESKTOP_FILE}"
    echo "[✓] Removed ${DESKTOP_FILE}"
fi

if [ -f "${ICON_FILE}" ]; then
    rm -f "${ICON_FILE}"
    echo "[✓] Removed ${ICON_FILE}"
fi

if [ -f "${PIXMAP_FILE}" ]; then
    rm -f "${PIXMAP_FILE}"
    echo "[✓] Removed ${PIXMAP_FILE}"
fi

# Restore backup AppImage if present
LUNAR_BAK="${HOME}/Lunar client/Lunar_Client.AppImage.bak"
if [ -f "${LUNAR_BAK}" ]; then
    read -p "Restore original unpatched Lunar Client AppImage? (Y/n): " DO_RESTORE
    DO_RESTORE=${DO_RESTORE:-Y}
    if [[ "$DO_RESTORE" =~ ^[Yy]$ ]]; then
        mv "${LUNAR_BAK}" "${HOME}/Lunar client/Lunar_Client.AppImage"
        echo "[✓] Restored original AppImage from backup."
    fi
fi

# Refresh desktop & icon databases
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v kbuildsycoca6 &>/dev/null; then
    kbuildsycoca6 --noincremental 2>/dev/null || true
elif command -v kbuildsycoca5 &>/dev/null; then
    kbuildsycoca5 --noincremental 2>/dev/null || true
fi

echo
echo "Uninstallation complete. Your offline account data remains in ~/.lunarclient/."
