# 🌙 Lunar Client Offline Manager (Linux & Windows)

A clean, native, and reliable offline account manager and patcher for **Lunar Client** on Linux (Fedora, Arch, Ubuntu, Debian) and Windows.

Allows you to play Minecraft offline with **custom usernames**, choose **any player's skin** (e.g. `Technoblade`, `Dream`, `MumboJumbo`, or custom names), and patches Lunar Client without breaking updates, corrupted hosts files, or socket crashes.

---

## ✨ Features

- 👤 **Add Offline Accounts**: Create and manage offline accounts with custom usernames.
- 🎨 **Skin Support via Mojang API**: Enter any Minecraft player's name in "Skin Name" and the tool will fetch their real Mojang UUID and textures so your skin renders both **in-game** and on Lunar Client's **topbar avatar**.
- 🛠️ **Non-Breaking AppImage Patcher**: Cleanly patches Lunar Client's internal authentication handler in `resources/app.asar` so offline accounts bypass Mojang license servers without affecting launcher stability or game files.
- 🔄 **Safe & Reversible**: Automatically keeps a backup (`Lunar_Client.AppImage.bak`) before applying any patch.
- 🖥️ **KDE Plasma Dark Theme GUI**: Built-in graphical user interface matching modern dark themes (Breeze Dark / Adwaita).
- ⚡ **Full CLI Support**: Fast command-line interface for terminal users and automation.
- 🚀 **1-Click Launch**: Directly launch Lunar Client with your active offline account.

---

## 📥 Quick 1-Command Installation (Linux)

If you ever reinstall your OS on a fresh drive or want to set this up quickly, simply run:

```bash
git clone https://github.com/phyrooshcodes/Lunarclient-off.git
cd Lunarclient-off
./install.sh
```

The installer will:
1. Verify Python 3 and `squashfs-tools`.
2. Install the `lunar-offline` command into `~/.local/bin/`.
3. Add a desktop shortcut to your Application Launcher (KDE Kickoff / GNOME App Grid).
4. Automatically detect and patch your Lunar Client AppImage.

---

## 🎮 How to Use

### 1. Graphical Interface (GUI)
- Launch **"Lunar Client Offline Manager"** from your application menu, or run:
  ```bash
  lunar-offline
  ```
- **Add Account**: Enter your desired **Username** and optional **Skin Name / Player** (e.g. `Technoblade`, `Dream`, `Steve`, etc.), then click **➕ Add / Update**.
- **Switch Active Account**: Select an account and click **⭐ Set as Active** (or double-click it).
- **Delete an Account**:
  - Select the account and click the red **🗑️ Delete Account** button, OR
  - Right-click the account and choose **Delete Account**, OR
  - Select the account and press the **`<Delete>`** or **`<BackSpace>`** key on your keyboard.
- **Remove All Accounts**: Click **🧹 Remove All** (or right-click -> Remove All Accounts).
- **Launch Game**: Click **🚀 Launch Lunar Client**!

### 2. Command Line (CLI)

```bash
# Open graphical manager:
lunar-offline gui

# Add an offline account with a skin:
lunar-offline add <Username> [SkinName]

# Examples:
lunar-offline add Phyroosh Technoblade
lunar-offline add Player123 Dream

# List all configured accounts:
lunar-offline list

# Switch the active account:
lunar-offline set-active Phyroosh

# Delete/remove a specific account:
lunar-offline delete Player123
lunar-offline remove Player123
lunar-offline rm Player123

# Interactive account deletion prompt:
lunar-offline delete

# Remove ALL accounts at once:
lunar-offline delete --all
lunar-offline remove --all

# Apply offline patch to Lunar Client AppImage:
lunar-offline patch

# Or specify a custom AppImage path:
lunar-offline patch --appimage /path/to/Lunar_Client.AppImage

# Launch Lunar Client:
lunar-offline launch
```

---

## 🪟 Windows Users

For Windows 11 / 10 users:
- Run `FixLunarOffline.bat` to restore and initialize offline functionality.

---

## 🛠️ Uninstallation

To remove the CLI command and desktop shortcut:

```bash
./uninstall.sh
```

---

## 📄 License

MIT License. Designed for offline play and personal customization.
