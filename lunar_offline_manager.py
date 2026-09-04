#!/usr/bin/env python3
"""
Lunar Client Offline Manager for Fedora Linux
=============================================
Allows adding and managing offline Minecraft accounts with custom skin names
and patching Lunar Client AppImage to enable offline play without breaking the launcher.
"""

import sys
import os
import re
import json
import struct
import shutil
import hashlib
import tempfile
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# Paths
HOME = Path.home()
LUNAR_DIR = HOME / ".lunarclient"
GAME_SETTINGS_DIR = LUNAR_DIR / "settings" / "game"
ACCOUNTS_FILE = GAME_SETTINGS_DIR / "accounts.json"
SAVED_SKINS_FILE = GAME_SETTINGS_DIR / "saved_skins.json"

DEFAULT_APPIMAGE_LOCATIONS = [
    HOME / "Lunar client" / "Lunar_Client.AppImage",
    HOME / "Downloads" / "Lunar_Client.AppImage",
    HOME / "Applications" / "Lunar_Client.AppImage",
    Path("/usr/local/bin/Lunar_Client.AppImage"),
]


def get_offline_uuid(username: str) -> str:
    """Computes standard Minecraft offline player UUID (version 3 MD5)."""
    val = f"OfflinePlayer:{username}".encode("utf-8")
    h = bytearray(hashlib.md5(val).digest())
    h[6] = (h[6] & 0x0F) | 0x30  # Version 3
    h[8] = (h[8] & 0x3F) | 0x80  # Variant RFC 4122
    return h.hex()


def resolve_skin(skin_name: str):
    """
    Queries Mojang API to fetch UUID and skin texture for the given skin name.
    Returns (uuid_hex, texture_url, model_type).
    Falls back to offline UUID if network fails or username not found.
    """
    skin_name = skin_name.strip()
    if not skin_name:
        return None, None, "classic"

    try:
        url = f"https://api.mojang.com/users/profiles/minecraft/{skin_name}"
        req = urllib.request.Request(url, headers={"User-Agent": "LunarOfflineManager/1.0"})
        with urllib.request.urlopen(req, timeout=5) as res:
            if res.status == 200:
                data = json.loads(res.read().decode("utf-8"))
                uuid_hex = data.get("id")
                
                # Fetch profile textures from session server
                session_url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid_hex}"
                s_req = urllib.request.Request(session_url, headers={"User-Agent": "LunarOfflineManager/1.0"})
                with urllib.request.urlopen(s_req, timeout=5) as s_res:
                    if s_res.status == 200:
                        s_data = json.loads(s_res.read().decode("utf-8"))
                        for prop in s_data.get("properties", []):
                            if prop.get("name") == "textures":
                                import base64
                                val = json.loads(base64.b64decode(prop.get("value")).decode("utf-8"))
                                textures = val.get("textures", {})
                                skin_info = textures.get("SKIN", {})
                                texture_url = skin_info.get("url")
                                model = skin_info.get("metadata", {}).get("model", "classic")
                                return uuid_hex, texture_url, model
                return uuid_hex, None, "classic"
    except Exception as e:
        print(f"[!] Note: Could not query Mojang API ({e}). Using offline player identity.")

    # Fallback to offline UUID
    return get_offline_uuid(skin_name), None, "classic"


def load_accounts():
    """Loads accounts from accounts.json."""
    if not ACCOUNTS_FILE.exists():
        return {"activeAccountLocalId": None, "accounts": {}}
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"activeAccountLocalId": None, "accounts": {}}


def save_accounts(data):
    """Saves accounts to accounts.json."""
    GAME_SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_offline_account(username: str, skin_name: str = ""):
    """
    Adds or updates an offline account with custom skin name.
    """
    username = username.strip()
    if not username:
        raise ValueError("Username cannot be empty.")

    skin_name = skin_name.strip() if skin_name else username
    skin_uuid, texture_url, skin_type = resolve_skin(skin_name)
    if not skin_uuid:
        skin_uuid = get_offline_uuid(username)

    local_id = f"offline_{hashlib.sha256(username.encode()).hexdigest()[:12]}"
    account_entry = {
        "accessToken": f"offline_token_{local_id}",
        "accessTokenExpiresAt": "2099-12-31T23:59:59.000Z",
        "localId": local_id,
        "minecraftProfile": {
            "id": skin_uuid,
            "name": username
        },
        "remoteId": f"remote_{local_id}",
        "type": "Xbox",
        "username": username,
        "eligibleForMigration": False,
        "hasMultipleProfiles": False,
        "legacy": False,
        "persistent": True,
        "userProperties": []
    }

    data = load_accounts()
    if "accounts" not in data or not isinstance(data["accounts"], dict):
        data["accounts"] = {}

    data["accounts"][local_id] = account_entry
    data["activeAccountLocalId"] = local_id
    save_accounts(data)

    # Save to saved_skins.json if texture URL is available
    if texture_url:
        try:
            saved_skins = {}
            if SAVED_SKINS_FILE.exists():
                with open(SAVED_SKINS_FILE, "r", encoding="utf-8") as f:
                    saved_skins = json.load(f)
            saved_skins[texture_url] = {
                "type": skin_type if skin_type in ("classic", "slim") else "classic",
                "name": skin_name
            }
            with open(SAVED_SKINS_FILE, "w", encoding="utf-8") as f:
                json.dump(saved_skins, f, indent=2)
        except Exception as e:
            print(f"[!] Warning: Could not update saved_skins.json: {e}")

    return account_entry


def set_active_account(username_or_id: str):
    """Sets the active account by username or localId."""
    data = load_accounts()
    accounts = data.get("accounts", {})
    target_id = None

    for lid, acc in accounts.items():
        if lid == username_or_id or acc.get("username", "").lower() == username_or_id.lower():
            target_id = lid
            break

    if not target_id:
        raise ValueError(f"Account '{username_or_id}' not found.")

    data["activeAccountLocalId"] = target_id
    save_accounts(data)
    return accounts[target_id]


def delete_account(username_or_id: str):
    """Removes an account from accounts.json."""
    data = load_accounts()
    accounts = data.get("accounts", {})
    target_id = None

    for lid, acc in accounts.items():
        if lid == username_or_id or acc.get("username", "").lower() == username_or_id.lower():
            target_id = lid
            break

    if not target_id:
        raise ValueError(f"Account '{username_or_id}' not found.")

    del accounts[target_id]
    if data.get("activeAccountLocalId") == target_id:
        data["activeAccountLocalId"] = next(iter(accounts.keys()), None)

    save_accounts(data)
    return True


def find_appimage(custom_path: str = None) -> Path:
    """Finds Lunar Client AppImage on the system."""
    if custom_path and Path(custom_path).is_file():
        return Path(custom_path)
    for p in DEFAULT_APPIMAGE_LOCATIONS:
        if p.is_file():
            return p
    raise FileNotFoundError("Could not locate Lunar Client AppImage. Please specify its path.")


# ==============================================================================
# ASAR Patching Utilities
# ==============================================================================

def patch_main_js(code_text: str) -> str:
    """Applies the clean offline validation bypass patch to main.js."""
    # 1. Update profiles mapping: don't flag offline accounts as invalid
    t1 = "invalid:!e.refreshToken"
    r1 = "invalid:!e.refreshToken&&!e.accessToken?.startsWith(`offline`)"
    if t1 in code_text and r1 not in code_text:
        code_text = code_text.replace(t1, r1)

    # 2. Add offline check in initAuthInternal before Mojang validation
    t2 = "try{nV.info(`Validating account ${r.minecraftProfile.name} owns Minecraft...`);"
    r2 = """if(r.accessToken?.startsWith(`offline`)){nV.info(`[Offline] Account ${r.minecraftProfile.name} authenticated in offline mode.`);Ea(`account.guest`,!1);Z.store.dispatch(fK({uuid:r.minecraftProfile.id,loading:!1}));return;}try{nV.info(`Validating account ${r.minecraftProfile.name} owns Minecraft...`);"""
    if t2 in code_text and "[Offline] Account" not in code_text:
        code_text = code_text.replace(t2, r2)

    # 3. Prevent 15s timeout for authenticator JWT requests on offline accounts
    t3 = "XV=async(e,t)=>{if(!e)throw new zB(WB.NO_ACCOUNT,`No account found for getting Lunar Client Token`);"
    r3 = "XV=async(e,t)=>{if(!e)throw new zB(WB.NO_ACCOUNT,`No account found for getting Lunar Client Token`);if(e.accessToken?.startsWith(`offline`))return`offline-jwt`;"
    if t3 in code_text and "offline-jwt" not in code_text:
        code_text = code_text.replace(t3, r3)

    return code_text


def update_asar_file(orig_asar_path: Path, target_rel_path: str, new_content_bytes: bytes, out_asar_path: Path):
    """
    Updates a file inside an ASAR archive in-place preserving exact Chromium Pickle format
    and all unpacked external modules.
    """
    with open(orig_asar_path, "rb") as f:
        header_raw = f.read(16)
        magic, s1, s2, json_size = struct.unpack("<IIII", header_raw)
        header = json.loads(f.read(json_size).decode("utf-8"))
        payload_base = f.tell()

        file_entries = []
        def traverse(tree, prefix=""):
            for name, info in tree.get("files", {}).items():
                rel = f"{prefix}/{name}" if prefix else name
                if "files" in info:
                    traverse(info, rel)
                elif not info.get("unpacked"):
                    file_entries.append((rel, info, int(info["offset"]), int(info["size"])))

        traverse(header)
        file_entries.sort(key=lambda x: x[2])

        new_payload = bytearray()
        cur_offset = 0
        for rel, node, offset, size in file_entries:
            if rel == target_rel_path:
                content = new_content_bytes
            else:
                f.seek(payload_base + offset)
                content = f.read(size)

            node["offset"] = str(cur_offset)
            node["size"] = len(content)
            cur_offset += len(content)
            new_payload.extend(content)

        new_json = json.dumps(header, separators=(",", ":")).encode("utf-8")
        j_len = len(new_json)
        pad = (4 - (j_len % 4)) % 4
        if pad:
            new_json += b" " * pad
            j_len = len(new_json)

        with open(out_asar_path, "wb") as out:
            out.write(struct.pack("<IIII", 4, j_len + 8, j_len + 4, j_len))
            out.write(new_json)
            out.write(new_payload)


def patch_appimage(appimage_path: Path, progress_callback=None):
    """
    Extracts Lunar Client AppImage, patches resources/app.asar,
    creates a backup (.bak), and repacks the AppImage.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    if not appimage_path.is_file():
        raise FileNotFoundError(f"AppImage not found at {appimage_path}")

    # Check unsquashfs and mksquashfs
    if not shutil.which("unsquashfs") or not shutil.which("mksquashfs"):
        raise RuntimeError("Missing 'unsquashfs' or 'mksquashfs'. Please install squashfs-tools.")

    # Create backup if not already present
    backup_path = appimage_path.with_suffix(".AppImage.bak")
    if not backup_path.exists():
        log(f"[*] Creating backup at: {backup_path.name}...")
        shutil.copy2(appimage_path, backup_path)

    with tempfile.TemporaryDirectory(prefix="lunar_patch_") as tmp_dir:
        tmp_dir = Path(tmp_dir)
        squash_dir = tmp_dir / "squashfs-root"
        runtime_path = tmp_dir / "runtime"
        repack_squashfs = tmp_dir / "repacked.squashfs"
        repack_appimage = tmp_dir / "repacked.AppImage"

        log("[1/5] Reading AppImage runtime header...")
        with open(appimage_path, "rb") as f:
            sq_offset = 188392 # Default AppImage Type 2 offset
            f.seek(0)
            runtime_bytes = f.read(sq_offset)
            with open(runtime_path, "wb") as rf:
                rf.write(runtime_bytes)

        log("[2/5] Extracting AppImage contents...")
        cmd_extract = ["unsquashfs", "-o", str(sq_offset), "-d", str(squash_dir), str(appimage_path)]
        res = subprocess.run(cmd_extract, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"unsquashfs failed: {res.stderr}")

        asar_path = squash_dir / "resources" / "app.asar"
        if not asar_path.is_file():
            raise FileNotFoundError("Could not find resources/app.asar inside AppImage.")

        log("[3/5] Extracting and patching main.js in app.asar...")
        with open(asar_path, "rb") as f:
            h_raw = f.read(16)
            magic, s1, s2, j_len = struct.unpack("<IIII", h_raw)
            header = json.loads(f.read(j_len).decode("utf-8"))
            p_base = f.tell()

            node = header["files"]["dist-electron"]["files"]["electron"]["files"]["main.js"]
            f.seek(p_base + int(node["offset"]))
            main_code = f.read(int(node["size"])).decode("utf-8", errors="ignore")

        if "[Offline] Account" in main_code:
            log("[i] AppImage is already patched for offline play!")
            return True

        patched_code = patch_main_js(main_code)
        # Verify patched code syntax using node
        if shutil.which("node"):
            test_js = tmp_dir / "test_main.js"
            with open(test_js, "w", encoding="utf-8") as f:
                f.write(patched_code)
            node_check = subprocess.run(["node", "-c", str(test_js)], capture_output=True)
            if node_check.returncode != 0:
                raise RuntimeError("Node syntax check failed on patched main.js")

        temp_asar = tmp_dir / "app.asar.patched"
        update_asar_file(asar_path, "dist-electron/electron/main.js", patched_code.encode("utf-8"), temp_asar)
        shutil.move(temp_asar, asar_path)

        log("[4/5] Repacking SquashFS filesystem...")
        cmd_mksquashfs = [
            "mksquashfs",
            str(squash_dir),
            str(repack_squashfs),
            "-comp", "gzip",
            "-b", "131072",
            "-no-xattrs",
            "-no-fragments"
        ]
        res_sq = subprocess.run(cmd_mksquashfs, capture_output=True, text=True)
        if res_sq.returncode != 0:
            raise RuntimeError(f"mksquashfs failed: {res_sq.stderr}")

        log("[5/5] Reassembling patched AppImage...")
        with open(repack_appimage, "wb") as out_f:
            with open(runtime_path, "rb") as rf:
                shutil.copyfileobj(rf, out_f)
            with open(repack_squashfs, "rb") as sf:
                shutil.copyfileobj(sf, out_f)

        os.chmod(repack_appimage, 0o755)
        shutil.move(str(repack_appimage), str(appimage_path))
        os.chmod(appimage_path, 0o755)

        log(f"[✓] Successfully patched {appimage_path.name}!")
        return True


def launch_lunar_client(appimage_path: Path):
    """Launches Lunar Client AppImage in background."""
    print(f"[*] Launching {appimage_path}...")
    subprocess.Popen([str(appimage_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


# ==============================================================================
# GUI Implementation (KDE Plasma Dark Theme Tkinter)
# ==============================================================================

def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox
    import io

    root = tk.Tk()
    root.title("Lunar Client Offline Manager")
    root.geometry("680x560")
    root.minsize(640, 520)

    # Style colors (KDE Breeze Dark inspired)
    BG_DARK = "#232629"
    BG_CARD = "#31363b"
    BG_INPUT = "#1b1e20"
    FG_TEXT = "#eff0f1"
    FG_MUTED = "#bdc3c7"
    ACCENT_GREEN = "#27ae60"
    ACCENT_BLUE = "#3daee9"
    ACCENT_RED = "#da4453"

    root.configure(bg=BG_DARK)

    # Variables
    username_var = tk.StringVar()
    skin_var = tk.StringVar()
    appimage_path_var = tk.StringVar()
    status_var = tk.StringVar(value="Ready")

    # Locate default AppImage
    try:
        default_appimage = find_appimage()
        appimage_path_var.set(str(default_appimage))
    except Exception:
        appimage_path_var.set("")

    # Styling
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=BG_DARK)
    style.configure("Card.TFrame", background=BG_CARD, relief="flat")
    style.configure("TLabel", background=BG_DARK, foreground=FG_TEXT, font=("Sans", 10))
    style.configure("Card.TLabel", background=BG_CARD, foreground=FG_TEXT, font=("Sans", 10))
    style.configure("Header.TLabel", background=BG_DARK, foreground=FG_TEXT, font=("Sans", 16, "bold"))
    style.configure("Muted.TLabel", background=BG_CARD, foreground=FG_MUTED, font=("Sans", 9))

    # Header
    header_frame = tk.Frame(root, bg=BG_DARK, pady=15)
    header_frame.pack(fill="x", padx=20)

    lbl_title = tk.Label(header_frame, text="🌙 Lunar Client Offline Manager", bg=BG_DARK, fg=FG_TEXT, font=("Sans", 16, "bold"))
    lbl_title.pack(side="left")

    lbl_sub = tk.Label(header_frame, text="Fedora KDE Edition", bg=BG_DARK, fg=ACCENT_BLUE, font=("Sans", 10, "italic"))
    lbl_sub.pack(side="left", padx=10, pady=(4, 0))

    # Notebook / Tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=20, pady=5)

    tab_accounts = tk.Frame(notebook, bg=BG_DARK, padx=15, pady=15)
    tab_patcher = tk.Frame(notebook, bg=BG_DARK, padx=15, pady=15)

    notebook.add(tab_accounts, text="  👤 Accounts  ")
    notebook.add(tab_patcher, text="  🛠️ Patcher & Settings  ")

    # --- TAB 1: ACCOUNTS ---
    form_card = tk.Frame(tab_accounts, bg=BG_CARD, bd=1, relief="ridge", padx=15, pady=15)
    form_card.pack(fill="x", pady=(0, 15))

    tk.Label(form_card, text="Add / Update Offline Account", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

    # Username Input
    tk.Label(form_card, text="Username:", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 10)).grid(row=1, column=0, sticky="w", pady=4)
    ent_user = tk.Entry(form_card, textvariable=username_var, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, font=("Sans", 10), width=24, relief="flat", bd=4)
    ent_user.grid(row=1, column=1, sticky="w", padx=10, pady=4)

    # Skin Input
    tk.Label(form_card, text="Skin Name / Player:", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 10)).grid(row=2, column=0, sticky="w", pady=4)
    ent_skin = tk.Entry(form_card, textvariable=skin_var, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, font=("Sans", 10), width=24, relief="flat", bd=4)
    ent_skin.grid(row=2, column=1, sticky="w", padx=10, pady=4)

    tk.Label(form_card, text="(e.g. Technoblade, Dream, Steve, or leave empty)", bg=BG_CARD, fg=FG_MUTED, font=("Sans", 8)).grid(row=3, column=1, sticky="w", padx=10)

    # Accounts List Section
    list_frame = tk.Frame(tab_accounts, bg=BG_CARD, bd=1, relief="ridge", padx=15, pady=15)
    list_frame.pack(fill="both", expand=True)

    tk.Label(list_frame, text="Configured Accounts", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 11, "bold")).pack(anchor="w", pady=(0, 5))

    list_container = tk.Frame(list_frame, bg=BG_CARD)
    list_container.pack(fill="both", expand=True)

    acc_listbox = tk.Listbox(list_container, bg=BG_INPUT, fg=FG_TEXT, selectbackground=ACCENT_BLUE, selectforeground="#ffffff", font=("Sans", 10), relief="flat", bd=4)
    acc_scrollbar = tk.Scrollbar(list_container, orient="vertical", command=acc_listbox.yview)
    acc_listbox.configure(yscrollcommand=acc_scrollbar.set)
    acc_listbox.pack(side="left", fill="both", expand=True)
    acc_scrollbar.pack(side="right", fill="y")

    # Helper to refresh list
    account_keys = []
    def refresh_accounts():
        nonlocal account_keys
        acc_listbox.delete(0, tk.END)
        account_keys = []
        data = load_accounts()
        active_id = data.get("activeAccountLocalId")
        accounts = data.get("accounts", {})
        for lid, acc in accounts.items():
            username = acc.get("username", "Unknown")
            is_active = " [ACTIVE]" if lid == active_id else ""
            acc_listbox.insert(tk.END, f"• {username}{is_active} (UUID: {acc.get('minecraftProfile', {}).get('id', '')[:8]}...)")
            account_keys.append(lid)

    def on_add_account():
        user = username_var.get().strip()
        skin = skin_var.get().strip()
        if not user:
            messagebox.showwarning("Input Required", "Please enter a Minecraft username.")
            return
        status_var.set(f"Adding account '{user}'...")
        root.update_idletasks()
        try:
            add_offline_account(user, skin)
            refresh_accounts()
            status_var.set(f"Account '{user}' added and set as active!")
            username_var.set("")
            skin_var.set("")
            messagebox.showinfo("Success", f"Offline account '{user}' created and set as active!")
        except Exception as err:
            status_var.set("Error adding account")
            messagebox.showerror("Error", f"Failed to add account: {err}")

    def on_set_active():
        sel = acc_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select Account", "Please select an account from the list.")
            return
        target_lid = account_keys[sel[0]]
        set_active_account(target_lid)
        refresh_accounts()
        status_var.set("Account set as active!")

    def on_delete_account():
        sel = acc_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select Account", "Please select an account to delete.")
            return
        target_lid = account_keys[sel[0]]
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this account?"):
            delete_account(target_lid)
            refresh_accounts()
            status_var.set("Account deleted.")

    # Action Buttons inside Accounts List
    btn_row = tk.Frame(list_frame, bg=BG_CARD, pady=10)
    btn_row.pack(fill="x")

    btn_add = tk.Button(form_card, text="➕ Add / Update", bg=ACCENT_GREEN, fg="#ffffff", activebackground="#219150", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=12, pady=6, command=on_add_account)
    btn_add.grid(row=4, column=1, sticky="w", padx=10, pady=8)

    btn_active = tk.Button(btn_row, text="⭐ Set as Active", bg=ACCENT_BLUE, fg="#ffffff", activebackground="#2980b9", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=10, pady=5, command=on_set_active)
    btn_active.pack(side="left", padx=(0, 10))

    btn_del = tk.Button(btn_row, text="🗑️ Delete", bg=ACCENT_RED, fg="#ffffff", activebackground="#c0392b", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=10, pady=5, command=on_delete_account)
    btn_del.pack(side="left")

    # --- TAB 2: PATCHER & SETTINGS ---
    patch_card = tk.Frame(tab_patcher, bg=BG_CARD, bd=1, relief="ridge", padx=15, pady=15)
    patch_card.pack(fill="both", expand=True)

    tk.Label(patch_card, text="Lunar Client AppImage Patcher", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 12, "bold")).pack(anchor="w", pady=(0, 10))

    tk.Label(patch_card, text="Target AppImage Path:", bg=BG_CARD, fg=FG_TEXT, font=("Sans", 10)).pack(anchor="w")

    path_row = tk.Frame(patch_card, bg=BG_CARD, pady=5)
    path_row.pack(fill="x")

    ent_path = tk.Entry(path_row, textvariable=appimage_path_var, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, font=("Sans", 9), relief="flat", bd=4)
    ent_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def on_browse():
        from tkinter import filedialog
        f = filedialog.askopenfilename(filetypes=[("AppImage Files", "*.AppImage"), ("All Files", "*")])
        if f:
            appimage_path_var.set(f)

    btn_browse = tk.Button(path_row, text="Browse...", bg=BG_INPUT, fg=FG_TEXT, font=("Sans", 9), relief="flat", padx=8, pady=4, command=on_browse)
    btn_browse.pack(side="right")

    info_lbl = tk.Label(patch_card, text="This patch modifies Lunar Client's internal authentication handler so that\noffline accounts are accepted directly without connecting to Mojang's license server.\nA backup (.bak) of your original AppImage will be kept automatically.", bg=BG_CARD, fg=FG_MUTED, font=("Sans", 9), justify="left")
    info_lbl.pack(anchor="w", pady=10)

    log_box = tk.Text(patch_card, height=10, bg=BG_INPUT, fg=FG_TEXT, font=("Monospace", 9), relief="flat", bd=4)
    log_box.pack(fill="both", expand=True, pady=5)

    def on_patch():
        p = appimage_path_var.get().strip()
        if not p or not Path(p).is_file():
            messagebox.showerror("Error", "Please select a valid Lunar Client AppImage file.")
            return

        log_box.delete("1.0", tk.END)
        def log_cb(msg):
            log_box.insert(tk.END, msg + "\n")
            log_box.see(tk.END)
            root.update_idletasks()

        try:
            status_var.set("Patching AppImage...")
            patch_appimage(Path(p), progress_callback=log_cb)
            status_var.set("Patching completed successfully!")
            messagebox.showinfo("Success", "Lunar Client AppImage patched successfully!\nYou can now launch and play offline.")
        except Exception as err:
            status_var.set("Patching failed")
            log_cb(f"[ERROR] {err}")
            messagebox.showerror("Patch Error", f"Failed to patch AppImage:\n{err}")

    btn_do_patch = tk.Button(patch_card, text="🛠️ Apply Offline Patch / Fix", bg=ACCENT_GREEN, fg="#ffffff", activebackground="#219150", activeforeground="#ffffff", font=("Sans", 10, "bold"), relief="flat", bd=0, padx=14, pady=8, command=on_patch)
    btn_do_patch.pack(anchor="w", pady=10)

    # Bottom Launch & Status Bar
    bottom_frame = tk.Frame(root, bg=BG_DARK, padx=20, pady=12)
    bottom_frame.pack(fill="x", side="bottom")

    status_lbl = tk.Label(bottom_frame, textvariable=status_var, bg=BG_DARK, fg=FG_MUTED, font=("Sans", 9))
    status_lbl.pack(side="left")

    def on_launch():
        p = appimage_path_var.get().strip()
        if not p or not Path(p).is_file():
            try:
                p = find_appimage()
            except Exception:
                messagebox.showerror("Error", "Could not find Lunar Client AppImage.")
                return
        status_var.set("Launching Lunar Client...")
        launch_lunar_client(Path(p))
        status_var.set("Lunar Client launched!")

    btn_launch = tk.Button(bottom_frame, text="🚀 Launch Lunar Client", bg=ACCENT_BLUE, fg="#ffffff", activebackground="#2980b9", activeforeground="#ffffff", font=("Sans", 10, "bold"), relief="flat", bd=0, padx=16, pady=8, command=on_launch)
    btn_launch.pack(side="right")

    refresh_accounts()
    root.mainloop()


# ==============================================================================
# CLI Implementation
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Lunar Client Offline Manager for Fedora Linux")
    subparsers = parser.add_subparsers(dest="command")

    # GUI command
    subparsers.add_parser("gui", help="Open the graphical interface (default)")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add or update an offline account")
    add_parser.add_argument("username", help="Player Minecraft username")
    add_parser.add_argument("skin", nargs="?", default="", help="Skin name or player to copy skin from (optional)")

    # List command
    subparsers.add_parser("list", help="List configured accounts")

    # Set active command
    set_parser = subparsers.add_parser("set-active", help="Set the active account")
    set_parser.add_argument("account", help="Username or account ID")

    # Delete command
    del_parser = subparsers.add_parser("delete", help="Delete an account")
    del_parser.add_argument("account", help="Username or account ID")

    # Patch command
    patch_parser = subparsers.add_parser("patch", help="Patch Lunar Client AppImage for offline play")
    patch_parser.add_argument("--appimage", "-a", help="Path to Lunar_Client.AppImage (optional)")

    # Launch command
    launch_parser = subparsers.add_parser("launch", help="Launch Lunar Client AppImage")
    launch_parser.add_argument("--appimage", "-a", help="Path to Lunar_Client.AppImage (optional)")

    args = parser.parse_args()

    if not args.command or args.command == "gui":
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            run_gui()
        else:
            parser.print_help()
    elif args.command == "add":
        acc = add_offline_account(args.username, args.skin)
        print(f"[✓] Added offline account: {acc['username']}")
        print(f"    Skin UUID: {acc['minecraftProfile']['id']}")
        print(f"    Active: YES")
    elif args.command == "list":
        data = load_accounts()
        active_id = data.get("activeAccountLocalId")
        accounts = data.get("accounts", {})
        print(f"Total Accounts: {len(accounts)}")
        print("-" * 50)
        for lid, acc in accounts.items():
            active_str = " [ACTIVE]" if lid == active_id else ""
            print(f"• {acc.get('username')}{active_str}")
            print(f"  ID: {lid}")
            print(f"  UUID: {acc.get('minecraftProfile', {}).get('id')}")
            print(f"  Type: {acc.get('type')}")
            print()
    elif args.command == "set-active":
        acc = set_active_account(args.account)
        print(f"[✓] Set '{acc['username']}' as active account.")
    elif args.command == "delete":
        delete_account(args.account)
        print(f"[✓] Deleted account '{args.account}'.")
    elif args.command == "patch":
        target = Path(args.appimage) if args.appimage else find_appimage()
        print(f"[*] Target AppImage: {target}")
        patch_appimage(target)
    elif args.command == "launch":
        target = Path(args.appimage) if args.appimage else find_appimage()
        launch_lunar_client(target)


if __name__ == "__main__":
    main()
