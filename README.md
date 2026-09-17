# 🌙 Lunar Client Offline Manager (Linux & Windows)

A clean, native, and reliable offline account manager and patcher for **Lunar Client** on **all Linux distributions** (Arch, Fedora, Ubuntu, Linux Mint, Debian, openSUSE, and more) and Windows.

Allows you to play Minecraft offline with **custom usernames**, choose **any player's skin** (e.g. `Technoblade`, `Dream`, `MumboJumbo`, or custom names), and patches Lunar Client without breaking updates, corrupted hosts files, or socket crashes.

---

## ✨ Features

- 👤 **Add Offline Accounts**: Create and manage offline accounts with custom usernames.
- 🎨 **Skin Support via Mojang API**: Enter any Minecraft player's name in "Skin Name" and the tool will fetch their real Mojang UUID and textures so your skin renders both **in-game** and on Lunar Client's **topbar avatar**.
- 🛠️ **Non-Breaking AppImage Patcher**: Cleanly patches Lunar Client's internal authentication handler in `resources/app.asar` so offline accounts bypass Mojang license servers without affecting launcher stability or game files.
- 🔄 **Safe & Reversible**: Automatically keeps a backup (`Lunar_Client.AppImage.bak`) before applying any patch.
- 🖥️ **Adaptive Dark Theme GUI**: Built-in graphical user interface matching modern dark themes (KDE Breeze Dark, GNOME Adwaita, Cinnamon, etc.) with automatic distro branding.
- ⌨️ **Interactive Terminal Menu (CLI)**: Zero-dependency interactive menu for terminal enthusiasts, headless servers, or environments without Tkinter.
- 🚀 **1-Click Launch**: Directly launch Lunar Client with your active offline account.
- 🌐 **Universal Linux Compatibility**: Fully automated installer and runtime support across all major package managers (`pacman`, `dnf`, `apt`, `zypper`, `apk`, `xbps`).

---

## 🐧 Multi-Distro Support & Prerequisites

The installer automatically detects your distro and installs all prerequisites for you. If you prefer to install packages manually, see below:

| Distribution | Package Manager | Install Command |
| :--- | :--- | :--- |
| **Arch Linux / Manjaro / EndeavourOS** | `pacman` | `sudo pacman -S --needed python tk squashfs-tools fuse2` |
| **Fedora / RHEL / Rocky / AlmaLinux** | `dnf` | `sudo dnf install python3 python3-tkinter squashfs-tools fuse-libs` |
| **Ubuntu / Debian / Linux Mint / Pop!_OS** | `apt` | `sudo apt update && sudo apt install python3 python3-tk squashfs-tools libfuse2` *(or `libfuse2t64` on 24.04+)* |
| **openSUSE (Tumbleweed / Leap)** | `zypper` | `sudo zypper install python3 python3-tk squashfs fuse` |
| **Alpine Linux** | `apk` | `sudo apk add python3 py3-tkinter squashfs-tools fuse` |
| **Void Linux** | `xbps` | `sudo xbps-install -y python3 python3-tkinter squashfs-tools fuse` |

---

## 📥 Quick 1-Command Installation (Linux)

If you ever reinstall your OS on a fresh drive or want to set this up quickly, simply run:

```bash
git clone https://github.com/phyroosh/LunarClient-off.git
cd LunarClient-off
./install.sh
```

The installer will:
1. Detect your Linux distribution and automatically install dependencies (`python3`, `tkinter`, `squashfs-tools`, `libfuse2`).
2. Install the `lunar-offline` command into `~/.local/bin/` and configure your shell `PATH` (`bash`, `zsh`, `fish`).
3. Install high-resolution application icons and a desktop shortcut into your Application Launcher (KDE Kickoff, GNOME App Grid, Cinnamon, XFCE).
4. Automatically search for Lunar Client AppImage across standard directories and offer to patch it immediately.

---

## 🎮 How to Use

### 1. Graphical Interface (GUI)
- Launch **"Lunar Client Offline Manager"** from your application menu, or run:
  ```bash
  lunar-offline
  ```
- **Add Account**: Enter your desired **Username** and optional **Skin Name / Player** (e.g. `Technoblade`, `Dream`, `Steve`), then click **➕ Add / Update**.
- **Switch Active Account**: Select an account and click **⭐ Set as Active** (or double-click it).
- **Delete an Account**:
  - Select the account and click the red **🗑️ Delete Account** button, OR
  - Right-click the account and choose **Delete Account**, OR
  - Select the account and press the **`<Delete>`** or **`<BackSpace>`** key on your keyboard.
- **Remove All Accounts**: Click **🧹 Remove All** (or right-click -> Remove All Accounts).
- **Launch Game**: Click **🚀 Launch Lunar Client**!

---

### 2. Interactive Terminal Menu (CLI Menu)

If you're over SSH, prefer the terminal, or don't have graphical libraries:

```bash
lunar-offline menu
# or
lunar-offline cli
```

Presents a clean, numbered interactive menu:
```text
=======================================================
     🌙 Lunar Client Offline Manager (CLI Menu)
=======================================================
  1. Add / Update Offline Account
  2. List Configured Accounts
  3. Set Active Account
  4. Delete an Account
  5. Remove ALL Accounts
  6. Apply Offline Patch to AppImage
  7. Launch Lunar Client
  8. Exit
-------------------------------------------------------
Please select an option (1-8):
```

---

### 3. Command Line (CLI Direct Commands)

```bash
# Open graphical manager:
lunar-offline gui

# Open interactive terminal menu:
lunar-offline menu

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

## 🪟 Windows Setup & Usage (Windows 10 & 11)

No complicated setup or `.exe` installer is needed! Simply double-click the included `.bat` file to open the Graphical User Interface:

### 1. 1-Click Graphical Interface (GUI)
- Double-click **`LunarOffline.bat`** (or **`FixLunarOffline.bat`**) to open the GUI.
- **Zero-Dependency Guarantee**:
  - If **Python 3** is installed on your PC, it immediately launches the fast Tkinter Dark Theme GUI.
  - If Python is **not** installed, it automatically launches the built-in native **PowerShell GUI** (works on 100% of Windows 10 and 11 computers out of the box with no extra downloads!).
  - You can also optionally install Python in 15 seconds via `winget install --id Python.Python.3.12 -e`.
- **Features in the Windows GUI**:
  - 👤 **Add / Update Accounts**: Type your username and skin name, click **➕ Add / Update**.
  - ⭐ **Set Active Account**: Choose an account and click **Set as Active** (or double-click it).
  - 🗑️ **Delete Account**: Remove individual accounts or all accounts with confirmation.
  - 🛠️ **1-Click ASAR Patcher**: Click **Apply Offline Patch / Fix** to patch `%LOCALAPPDATA%\Programs\lunarclient\resources\app.asar`. A backup (`app.asar.bak`) is created automatically.
  - 🚀 **Launch**: Click **🚀 Launch Lunar Client** to play offline immediately!

### 2. Windows Command Line (CMD / PowerShell)
You can also run all actions directly from Command Prompt or PowerShell:

```cmd
:: Open Graphical Interface:
LunarOffline.bat

:: Add account with custom skin:
LunarOffline.bat add Phyroosh Technoblade
LunarOffline.bat add Player123 Dream

:: List configured accounts:
LunarOffline.bat list

:: Set active account:
LunarOffline.bat set-active Phyroosh

:: Delete an account:
LunarOffline.bat delete Player123

:: Apply offline patch to app.asar:
LunarOffline.bat patch

:: Launch Lunar Client:
LunarOffline.bat launch
```

---

## 🛠️ Uninstallation

To remove the Linux desktop shortcut, icons, and command:

```bash
./uninstall.sh
```

---

## 📄 License

MIT License. Designed for offline play and personal customization.

