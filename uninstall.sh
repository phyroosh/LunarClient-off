#!/usr/bin/env bash
set -e

BIN_FILE="${HOME}/.local/bin/lunar-offline"
DESKTOP_FILE="${HOME}/.local/share/applications/lunar-offline.desktop"

echo "========================================================"
echo "      Lunar Client Offline Manager - Uninstaller"
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

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
fi

echo
echo "Uninstallation complete. Your offline account data remains in ~/.lunarclient/."
