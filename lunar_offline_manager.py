#!/usr/bin/env python3
"""
Lunar Client Offline Manager for Windows & Linux
=================================================
Allows adding and managing offline Minecraft accounts with custom skin names
and patching Lunar Client to enable offline play without breaking the launcher.
Supports: Windows 10/11 and all Linux distributions (Arch, Fedora, Ubuntu, Mint, Debian, etc.).
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
import datetime
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# System & Paths
IS_WINDOWS = sys.platform == "win32"
HOME = Path.home()
LUNAR_DIR = HOME / ".lunarclient"
GAME_SETTINGS_DIR = LUNAR_DIR / "settings" / "game"
ACCOUNTS_FILE = GAME_SETTINGS_DIR / "accounts.json"
SAVED_SKINS_FILE = GAME_SETTINGS_DIR / "saved_skins.json"

if IS_WINDOWS:
    LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", str(HOME / "AppData" / "Local")))
    PROGRAMFILES = Path(os.environ.get("ProgramFiles", "C:\\Program Files"))
else:
    LOCALAPPDATA = HOME / ".local" / "share"
    PROGRAMFILES = Path("/usr/local")

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


def get_valid_expiry() -> str:
    """
    Computes an ISO-8601 UTC timestamp 7 days in the future.
    Critical requirements:
    1. Launcher requires (now < expiresAt) - cannot be expired.
    2. In-game lunar.jar requires (expiresAt <= now + 14 days) - if > 14 days,
       lunar.jar marks the account as 'invalid (2)' and deletes it!
    7 days from now satisfies both launcher and in-game checks perfectly.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now + datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def refresh_offline_accounts(data=None, save_if_modified: bool = True):
    """
    Refreshes accessTokenExpiresAt and ensures refreshToken is set for all offline accounts.
    Ensures accounts never expire and always pass lunar.jar validation.
    """
    save_needed = False
    if data is None:
        data = load_accounts(auto_refresh=False)
        save_needed = True

    accounts = data.get("accounts", {})
    if not isinstance(accounts, dict):
        accounts = {}
        data["accounts"] = accounts

    new_expiry = get_valid_expiry()

    for lid, acc in list(accounts.items()):
        is_offline = (
            lid.startswith("offline_")
            or str(acc.get("accessToken", "")).startswith("offline")
            or str(acc.get("refreshToken", "")).startswith("offline")
        )
        if is_offline:
            if not acc.get("refreshToken"):
                acc["refreshToken"] = f"offline_refresh_{lid}"
                save_needed = True
            if not acc.get("accessToken"):
                acc["accessToken"] = f"offline_token_{lid}"
                save_needed = True
            if acc.get("accessTokenExpiresAt") != new_expiry:
                acc["accessTokenExpiresAt"] = new_expiry
                save_needed = True
            if acc.get("type") != "Xbox":
                acc["type"] = "Xbox"
                save_needed = True

    if save_needed and save_if_modified:
        save_accounts(data)

    return data


def load_accounts(auto_refresh: bool = True):
    """Loads accounts from accounts.json."""
    if not ACCOUNTS_FILE.exists():
        return {"activeAccountLocalId": None, "accounts": {}}
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if auto_refresh and data.get("accounts"):
            refresh_offline_accounts(data, save_if_modified=True)
        return data
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
        "accessTokenExpiresAt": get_valid_expiry(),
        "localId": local_id,
        "minecraftProfile": {
            "id": skin_uuid,
            "name": username
        },
        "refreshToken": f"offline_refresh_{local_id}",
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


def delete_account(username_or_id: str) -> str:
    """Removes an account from accounts.json by username or localId. Returns deleted username."""
    data = load_accounts(auto_refresh=False)
    accounts = data.get("accounts", {})
    target_id = None

    for lid, acc in accounts.items():
        if lid == username_or_id or acc.get("username", "").lower() == username_or_id.lower():
            target_id = lid
            break

    if not target_id:
        raise ValueError(f"Account '{username_or_id}' not found.")

    deleted_name = accounts[target_id].get("username", target_id)
    del accounts[target_id]
    if data.get("activeAccountLocalId") == target_id:
        data["activeAccountLocalId"] = next(iter(accounts.keys()), None)

    save_accounts(data)
    return deleted_name


def delete_all_accounts():
    """Removes all accounts from accounts.json."""
    data = load_accounts(auto_refresh=False)
    data["accounts"] = {}
    data["activeAccountLocalId"] = None
    save_accounts(data)
    return True


def find_appimage(custom_path: str = None) -> Path:
    """Finds Lunar Client AppImage across all standard Linux paths and desktop directories."""
    if custom_path and Path(custom_path).is_file():
        return Path(custom_path)

    # 1. Exact common paths across distros (Fedora, Arch, Ubuntu, Mint, Debian, etc.)
    candidates = [
        HOME / "Lunar client" / "Lunar_Client.AppImage",
        HOME / "LunarClient" / "Lunar_Client.AppImage",
        HOME / "Applications" / "Lunar_Client.AppImage",
        HOME / "Downloads" / "Lunar_Client.AppImage",
        HOME / "Desktop" / "Lunar_Client.AppImage",
        HOME / ".local" / "bin" / "Lunar_Client.AppImage",
        HOME / ".local" / "share" / "applications" / "Lunar_Client.AppImage",
        Path("/usr/local/bin/Lunar_Client.AppImage"),
        Path("/opt/Lunar Client/Lunar_Client.AppImage"),
        Path("/opt/lunarclient/Lunar_Client.AppImage"),
        Path.cwd() / "Lunar_Client.AppImage",
    ]
    for p in candidates:
        if p.is_file():
            return p

    # 2. Case-insensitive search in common directories
    search_dirs = [
        HOME / "Lunar client",
        HOME / "LunarClient",
        HOME / "Applications",
        HOME / "Downloads",
        HOME / "Desktop",
        HOME / ".local" / "bin",
        Path.cwd(),
    ]
    for d in search_dirs:
        if d.is_dir():
            try:
                for item in d.iterdir():
                    if item.is_file() and item.name.lower().endswith(".appimage") and "lunar" in item.name.lower():
                        return item
            except Exception:
                pass

    raise FileNotFoundError("Could not locate Lunar Client AppImage. Please specify its path with --appimage.")


def find_windows_asar(custom_path: str = None) -> Path:
    """Finds Lunar Client resources/app.asar on Windows."""
    if custom_path and Path(custom_path).is_file():
        p = Path(custom_path)
        if p.name.lower() == "app.asar":
            return p
        if p.name.lower().endswith(".exe"):
            possible = p.parent / "resources" / "app.asar"
            if possible.is_file():
                return possible
        return p

    candidates = [
        LOCALAPPDATA / "Programs" / "lunarclient" / "resources" / "app.asar",
        LOCALAPPDATA / "Programs" / "Lunar Client" / "resources" / "app.asar",
        PROGRAMFILES / "Lunar Client" / "resources" / "app.asar",
        HOME / "AppData" / "Local" / "Programs" / "lunarclient" / "resources" / "app.asar",
        HOME / "AppData" / "Local" / "Programs" / "Lunar Client" / "resources" / "app.asar",
        Path("C:/Users") / HOME.name / "AppData/Local/Programs/lunarclient/resources/app.asar",
        Path("C:/Users") / HOME.name / "AppData/Local/Programs/Lunar Client/resources/app.asar",
        Path.cwd() / "resources" / "app.asar",
        Path.cwd() / "app.asar",
    ]
    for c in candidates:
        if c.is_file():
            return c

    # Search in Programs
    for base in [LOCALAPPDATA / "Programs", PROGRAMFILES]:
        if base.is_dir():
            try:
                for f in base.rglob("app.asar"):
                    if "lunar" in str(f).lower():
                        return f
            except Exception:
                pass

    raise FileNotFoundError("Could not locate Lunar Client app.asar on Windows. Please specify its path.")


def find_windows_launcher(custom_path: str = None) -> Path:
    """Finds Lunar Client.exe on Windows."""
    if custom_path and Path(custom_path).is_file():
        p = Path(custom_path)
        if p.name.lower().endswith(".exe"):
            return p
        if p.name.lower() == "app.asar":
            possible = p.parent.parent / "Lunar Client.exe"
            if possible.is_file():
                return possible
        return p

    candidates = [
        LOCALAPPDATA / "Programs" / "lunarclient" / "Lunar Client.exe",
        LOCALAPPDATA / "Programs" / "Lunar Client" / "Lunar Client.exe",
        PROGRAMFILES / "Lunar Client" / "Lunar Client.exe",
        HOME / "AppData" / "Local" / "Programs" / "lunarclient" / "Lunar Client.exe",
        HOME / "AppData" / "Local" / "Programs" / "Lunar Client" / "Lunar Client.exe",
        Path("C:/Users") / HOME.name / "AppData/Local/Programs/lunarclient/Lunar Client.exe",
        Path("C:/Users") / HOME.name / "AppData/Local/Programs/Lunar Client/Lunar Client.exe",
    ]
    for c in candidates:
        if c.is_file():
            return c

    for base in [LOCALAPPDATA / "Programs", PROGRAMFILES]:
        if base.is_dir():
            try:
                for f in base.rglob("Lunar Client.exe"):
                    return f
            except Exception:
                pass

    raise FileNotFoundError("Could not locate Lunar Client.exe on Windows.")


def find_target(custom_path: str = None) -> Path:
    """Finds target to patch (resources/app.asar on Windows, Lunar_Client.AppImage on Linux)."""
    if IS_WINDOWS:
        return find_windows_asar(custom_path)
    return find_appimage(custom_path)


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

    # 4. Handle refreshAccountInternal for offline accounts so token refreshes don't fail
    t4 = "async refreshAccountInternal(e){if(!e.refreshToken)throw new zB(WB.INVALID_SESSION,"
    r4 = "async refreshAccountInternal(e){if(e.accessToken?.startsWith(`offline`)){nV.info(`[Offline] Account ${e.minecraftProfile?.name} refreshed locally.`);e.accessTokenExpiresAt=new Date(Date.now()+7*864e5).toISOString();let i=await pV();if(i.accounts[e.localId]){i.accounts[e.localId].accessTokenExpiresAt=e.accessTokenExpiresAt;await mV(i);}return e;}if(!e.refreshToken)throw new zB(WB.INVALID_SESSION,"
    if t4 in code_text and "refreshed locally" not in code_text:
        code_text = code_text.replace(t4, r4)

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

        if "[Offline] Account" in main_code and "refreshed locally" in main_code:
            log("[i] AppImage is already fully patched for offline play!")
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
        target_tmp = appimage_path.with_name(appimage_path.name + ".tmp")
        shutil.copy2(repack_appimage, target_tmp)
        os.chmod(target_tmp, 0o755)
        os.replace(target_tmp, appimage_path)

        log(f"[✓] Successfully patched {appimage_path.name}!")
        return True


def patch_windows_asar(asar_path: Path, progress_callback=None):
    """
    Patches resources/app.asar directly on Windows without squashfs.
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    if not asar_path.is_file():
        raise FileNotFoundError(f"app.asar not found at: {asar_path}")

    backup_path = asar_path.with_name("app.asar.bak")
    if not backup_path.exists():
        log(f"[*] Creating backup at: {backup_path.name}...")
        shutil.copy2(asar_path, backup_path)

    log("[1/3] Reading app.asar...")
    with open(asar_path, "rb") as f:
        h_raw = f.read(16)
        magic, s1, s2, j_len = struct.unpack("<IIII", h_raw)
        header = json.loads(f.read(j_len).decode("utf-8"))
        p_base = f.tell()

        node = header["files"]["dist-electron"]["files"]["electron"]["files"]["main.js"]
        f.seek(p_base + int(node["offset"]))
        main_code = f.read(int(node["size"])).decode("utf-8", errors="ignore")

    if "[Offline] Account" in main_code and "refreshed locally" in main_code:
        log("[i] Lunar Client is already patched for offline play!")
        return True

    log("[2/3] Applying offline patch to main.js...")
    patched_code = patch_main_js(main_code)

    log("[3/3] Writing updated app.asar...")
    temp_asar = asar_path.with_name("app.asar.tmp")
    update_asar_file(asar_path, "dist-electron/electron/main.js", patched_code.encode("utf-8"), temp_asar)

    if temp_asar.exists():
        os.replace(temp_asar, asar_path)

    log("[✓] Successfully patched Lunar Client for Windows!")
    return True


def patch_target(target_path: Path = None, progress_callback=None):
    """Applies offline patch to Lunar Client on either Windows or Linux."""
    if IS_WINDOWS:
        target = target_path if target_path else find_windows_asar()
        return patch_windows_asar(target, progress_callback)
    else:
        target = target_path if target_path else find_appimage()
        return patch_appimage(target, progress_callback)


def launch_lunar_client(target_path: Path = None):
    """Launches Lunar Client (Lunar Client.exe on Windows, AppImage on Linux)."""
    refresh_offline_accounts()
    if IS_WINDOWS:
        exe_path = target_path if (target_path and target_path.name.lower().endswith(".exe")) else find_windows_launcher()
        print(f"[*] Launching Lunar Client Windows: {exe_path}...")
        subprocess.Popen([str(exe_path)])
    else:
        appimage_path = target_path if target_path else find_appimage()
        print(f"[*] Launching {appimage_path} (using NVIDIA Dedicated GPU)...")
        env = os.environ.copy()
        env.update({
            "__NV_PRIME_RENDER_OFFLOAD": "1",
            "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
            "__VK_LAYER_NV_optimus": "NVIDIA_only",
            "VK_LOADER_DRIVERS_SELECT": "*nvidia*",
        })
        subprocess.Popen([str(appimage_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=env)


# ==============================================================================
# GUI Implementation (Dark Theme Tkinter - Windows & Linux)
# ==============================================================================

def get_distro_display_name() -> str:
    """Returns a friendly distro or OS name like 'Windows 11', 'Fedora Linux', etc."""
    if IS_WINDOWS:
        import platform
        rel = platform.release()
        return f"Windows {rel}" if rel else "Windows"
    try:
        os_release = Path("/etc/os-release")
        if os_release.is_file():
            with open(os_release, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return "Linux"


def run_gui():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("\n" + "=" * 65)
        print("  [!] Notice: Python Tkinter is not installed on this system.")
        print("  To enable the graphical interface, install it with:")
        print("    • Ubuntu / Debian / Mint:  sudo apt install python3-tk")
        print("    • Fedora / RHEL / Rocky:   sudo dnf install python3-tkinter")
        print("    • Arch / Manjaro:          sudo pacman -S tk")
        print("    • openSUSE:                sudo zypper install python3-tk")
        print("=" * 65)
        print("[*] Starting interactive terminal menu instead...\n")
        run_interactive_cli()
        return

    import io

    root = tk.Tk()
    root.title("Lunar Client Offline Manager")
    root.geometry("680x560")
    root.minsize(640, 520)

    # Window icon
    icon_candidates = [
        Path(__file__).parent / "icon.png",
        HOME / ".local" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "lunar-offline.png",
        HOME / ".local" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "lunarclient.png",
        HOME / ".local" / "share" / "pixmaps" / "lunar-offline.png",
    ]
    for ic in icon_candidates:
        if ic.is_file():
            try:
                win_icon = tk.PhotoImage(file=str(ic))
                root.iconphoto(False, win_icon)
                break
            except Exception:
                pass

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
    target_path_var = tk.StringVar()
    status_var = tk.StringVar(value="Ready")

    # Locate default Target (app.asar on Windows, AppImage on Linux)
    try:
        default_target = find_target()
        target_path_var.set(str(default_target))
    except Exception:
        target_path_var.set("")

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

    distro_name = get_distro_display_name()
    lbl_sub = tk.Label(header_frame, text=f"{distro_name} Edition", bg=BG_DARK, fg=ACCENT_BLUE, font=("Sans", 10, "italic"))
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

    # Action Buttons inside Accounts List (docked to bottom so ALWAYS visible)
    btn_row = tk.Frame(list_frame, bg=BG_CARD, pady=8)
    btn_row.pack(fill="x", side="bottom")

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
        data = load_accounts(auto_refresh=False)
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
            messagebox.showwarning("Select Account", "Please select an account from the list to delete.")
            return
        target_lid = account_keys[sel[0]]
        data = load_accounts(auto_refresh=False)
        acc_name = data.get("accounts", {}).get(target_lid, {}).get("username", target_lid)
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete offline account '{acc_name}'?"):
            delete_account(target_lid)
            refresh_accounts()
            status_var.set(f"Account '{acc_name}' deleted.")
            messagebox.showinfo("Deleted", f"Account '{acc_name}' was removed.")

    def on_delete_all():
        if not account_keys:
            messagebox.showinfo("No Accounts", "There are no accounts to remove.")
            return
        if messagebox.askyesno("Confirm Delete All", "Are you sure you want to remove ALL offline accounts?"):
            delete_all_accounts()
            refresh_accounts()
            status_var.set("All accounts removed.")
            messagebox.showinfo("Removed", "All offline accounts have been removed.")

    # Context Menu for right-click on accounts list
    ctx_menu = tk.Menu(acc_listbox, tearoff=0, bg=BG_CARD, fg=FG_TEXT, activebackground=ACCENT_BLUE, activeforeground="#ffffff")
    ctx_menu.add_command(label="⭐ Set as Active", command=on_set_active)
    ctx_menu.add_command(label="🗑️ Delete Account", command=on_delete_account)
    ctx_menu.add_separator()
    ctx_menu.add_command(label="🧹 Remove All Accounts", command=on_delete_all)

    def on_right_click(event):
        idx = acc_listbox.nearest(event.y)
        if idx >= 0 and idx < len(account_keys):
            acc_listbox.selection_clear(0, tk.END)
            acc_listbox.selection_set(idx)
            acc_listbox.activate(idx)
            ctx_menu.tk_popup(event.x_root, event.y_root)

    acc_listbox.bind("<Button-3>", on_right_click)
    acc_listbox.bind("<Delete>", lambda e: on_delete_account())
    acc_listbox.bind("<BackSpace>", lambda e: on_delete_account())
    acc_listbox.bind("<Double-Button-1>", lambda e: on_set_active())
    acc_listbox.bind("<Return>", lambda e: on_set_active())

    # Buttons in Accounts List
    btn_add = tk.Button(form_card, text="➕ Add / Update", bg=ACCENT_GREEN, fg="#ffffff", activebackground="#219150", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=12, pady=6, command=on_add_account)
    btn_add.grid(row=4, column=1, sticky="w", padx=10, pady=8)

    btn_active = tk.Button(btn_row, text="⭐ Set as Active", bg=ACCENT_BLUE, fg="#ffffff", activebackground="#2980b9", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=12, pady=6, command=on_set_active)
    btn_active.pack(side="left", padx=(0, 8))

    btn_del = tk.Button(btn_row, text="🗑️ Delete Account", bg=ACCENT_RED, fg="#ffffff", activebackground="#c0392b", activeforeground="#ffffff", font=("Sans", 9, "bold"), relief="flat", bd=0, padx=12, pady=6, command=on_delete_account)
    btn_del.pack(side="left", padx=(0, 8))

    btn_del_all = tk.Button(btn_row, text="🧹 Remove All", bg="#5a6268", fg="#ffffff", activebackground="#4e555b", activeforeground="#ffffff", font=("Sans", 9), relief="flat", bd=0, padx=10, pady=6, command=on_delete_all)
    btn_del_all.pack(side="left")

    # --- TAB 2: PATCHER & SETTINGS ---
    patch_card = tk.Frame(tab_patcher, bg=BG_CARD, bd=1, relief="ridge", padx=15, pady=15)
    patch_card.pack(fill="both", expand=True)

    patcher_title = "Lunar Client Patcher & Settings"
    tk.Label(patch_card, text=patcher_title, bg=BG_CARD, fg=FG_TEXT, font=("Sans", 12, "bold")).pack(anchor="w", pady=(0, 10))

    target_label_text = "Target Path (app.asar or Lunar Client.exe):" if IS_WINDOWS else "Target AppImage Path:"
    tk.Label(patch_card, text=target_label_text, bg=BG_CARD, fg=FG_TEXT, font=("Sans", 10)).pack(anchor="w")

    path_row = tk.Frame(patch_card, bg=BG_CARD, pady=5)
    path_row.pack(fill="x")

    ent_path = tk.Entry(path_row, textvariable=target_path_var, bg=BG_INPUT, fg=FG_TEXT, insertbackground=FG_TEXT, font=("Sans", 9), relief="flat", bd=4)
    ent_path.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def on_browse():
        from tkinter import filedialog
        if IS_WINDOWS:
            f = filedialog.askopenfilename(filetypes=[("Lunar Client Files", "*.asar;*.exe"), ("ASAR Archive", "*.asar"), ("Executable", "*.exe"), ("All Files", "*")])
        else:
            f = filedialog.askopenfilename(filetypes=[("AppImage Files", "*.AppImage"), ("All Files", "*")])
        if f:
            target_path_var.set(f)

    btn_browse = tk.Button(path_row, text="Browse...", bg=BG_INPUT, fg=FG_TEXT, font=("Sans", 9), relief="flat", padx=8, pady=4, command=on_browse)
    btn_browse.pack(side="right")

    if IS_WINDOWS:
        info_text = (
            "This patch modifies Lunar Client's internal authentication handler in app.asar so that\n"
            "offline accounts are accepted directly without connecting to Mojang's license server.\n"
            "A backup (app.asar.bak) of your original file will be created automatically."
        )
    else:
        info_text = (
            "This patch modifies Lunar Client's internal authentication handler so that\n"
            "offline accounts are accepted directly without connecting to Mojang's license server.\n"
            "A backup (.bak) of your original AppImage will be kept automatically."
        )

    info_lbl = tk.Label(patch_card, text=info_text, bg=BG_CARD, fg=FG_MUTED, font=("Sans", 9), justify="left")
    info_lbl.pack(anchor="w", pady=10)

    log_box = tk.Text(patch_card, height=10, bg=BG_INPUT, fg=FG_TEXT, font=("Monospace", 9), relief="flat", bd=4)
    log_box.pack(fill="both", expand=True, pady=5)

    def on_patch():
        p = target_path_var.get().strip()
        if not p or not Path(p).is_file():
            target_name = "app.asar or Lunar Client.exe" if IS_WINDOWS else "Lunar Client AppImage"
            messagebox.showerror("Error", f"Please select a valid {target_name} file.")
            return

        log_box.delete("1.0", tk.END)
        def log_cb(msg):
            log_box.insert(tk.END, msg + "\n")
            log_box.see(tk.END)
            root.update_idletasks()

        try:
            status_var.set("Patching Lunar Client...")
            patch_target(Path(p), progress_callback=log_cb)
            status_var.set("Patching completed successfully!")
            messagebox.showinfo("Success", "Lunar Client patched successfully!\nYou can now launch and play offline.")
        except Exception as err:
            status_var.set("Patching failed")
            log_cb(f"[ERROR] {err}")
            messagebox.showerror("Patch Error", f"Failed to patch Lunar Client:\n{err}")

    btn_do_patch = tk.Button(patch_card, text="🛠️ Apply Offline Patch / Fix", bg=ACCENT_GREEN, fg="#ffffff", activebackground="#219150", activeforeground="#ffffff", font=("Sans", 10, "bold"), relief="flat", bd=0, padx=14, pady=8, command=on_patch)
    btn_do_patch.pack(anchor="w", pady=10)

    # Bottom Launch & Status Bar
    bottom_frame = tk.Frame(root, bg=BG_DARK, padx=20, pady=12)
    bottom_frame.pack(fill="x", side="bottom")

    status_lbl = tk.Label(bottom_frame, textvariable=status_var, bg=BG_DARK, fg=FG_MUTED, font=("Sans", 9))
    status_lbl.pack(side="left")

    def on_launch():
        p = target_path_var.get().strip()
        target = Path(p) if (p and Path(p).is_file()) else None
        status_var.set("Launching Lunar Client...")
        try:
            launch_lunar_client(target)
            status_var.set("Lunar Client launched!")
        except Exception as err:
            status_var.set("Launch failed")
            messagebox.showerror("Launch Error", f"Failed to launch Lunar Client:\n{err}")

    btn_launch = tk.Button(bottom_frame, text="🚀 Launch Lunar Client", bg=ACCENT_BLUE, fg="#ffffff", activebackground="#2980b9", activeforeground="#ffffff", font=("Sans", 10, "bold"), relief="flat", bd=0, padx=16, pady=8, command=on_launch)
    btn_launch.pack(side="right")

    refresh_accounts()
    root.mainloop()


# ==============================================================================
# Interactive CLI Menu (Zero Dependencies, works on any terminal/distro)
# ==============================================================================

def run_interactive_cli():
    """Interactive command-line interface when GUI is not available or requested."""
    while True:
        os_label = "Windows" if IS_WINDOWS else get_distro_display_name()
        print("\n" + "=" * 55)
        print(f"     🌙 Lunar Client Offline Manager ({os_label})")
        print("=" * 55)
        print("  1. Add / Update Offline Account")
        print("  2. List Configured Accounts")
        print("  3. Set Active Account")
        print("  4. Delete an Account")
        print("  5. Remove ALL Accounts")
        patch_label = "Apply Offline Patch (app.asar)" if IS_WINDOWS else "Apply Offline Patch (AppImage)"
        print(f"  6. {patch_label}")
        print("  7. Launch Lunar Client")
        print("  8. Exit")
        print("-" * 55)
        try:
            choice = input("Please select an option (1-8): ").strip()
            if choice == "1":
                user = input("Enter Minecraft Username: ").strip()
                if not user:
                    print("[!] Username cannot be empty.")
                    continue
                skin = input("Enter Skin Player Name (or press Enter to use same): ").strip()
                acc = add_offline_account(user, skin)
                print(f"[✓] Added and activated offline account '{acc['username']}'.")
            elif choice == "2":
                data = load_accounts()
                active_id = data.get("activeAccountLocalId")
                accounts = data.get("accounts", {})
                print(f"\nTotal Accounts: {len(accounts)}")
                print("-" * 40)
                for lid, acc in accounts.items():
                    act = " [ACTIVE]" if lid == active_id else ""
                    print(f"• {acc.get('username')}{act} (UUID: {acc.get('minecraftProfile', {}).get('id', '')[:8]}...)")
            elif choice == "3":
                acc_name = input("Enter Username or ID to set active: ").strip()
                if acc_name:
                    try:
                        acc = set_active_account(acc_name)
                        print(f"[✓] Set '{acc['username']}' as active account.")
                    except Exception as e:
                        print(f"[!] {e}")
            elif choice == "4":
                acc_name = input("Enter Username or ID to delete: ").strip()
                if acc_name:
                    try:
                        username = delete_account(acc_name)
                        print(f"[✓] Deleted account '{username}'.")
                    except Exception as e:
                        print(f"[!] {e}")
            elif choice == "5":
                confirm = input("Are you sure you want to remove ALL accounts? (y/N): ").strip()
                if confirm.lower() in ("y", "yes"):
                    delete_all_accounts()
                    print("[✓] All accounts have been removed.")
            elif choice == "6":
                target_desc = "app.asar or Lunar Client.exe" if IS_WINDOWS else "AppImage path"
                custom_path = input(f"Enter {target_desc} (or press Enter for auto-detect): ").strip()
                try:
                    target = find_target(custom_path if custom_path else None)
                    print(f"[*] Patching {target}...")
                    patch_target(target)
                except Exception as e:
                    print(f"[!] Error: {e}")
            elif choice == "7":
                try:
                    launch_lunar_client()
                except Exception as e:
                    print(f"[!] Error: {e}")
            elif choice in ("8", "exit", "q", "quit"):
                print("Goodbye!")
                break
            else:
                print("[!] Invalid choice. Please enter 1-8.")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break


# ==============================================================================
# CLI Implementation
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Lunar Client Offline Manager for Windows & Linux (Arch, Fedora, Ubuntu, Mint, Debian & all distros)")
    subparsers = parser.add_subparsers(dest="command")

    # GUI command
    subparsers.add_parser("gui", help="Open the graphical interface (default)")

    # Interactive CLI menu
    for cmd in ("menu", "cli", "interactive"):
        subparsers.add_parser(cmd, help="Open interactive terminal menu")

    # Add command
    add_parser = subparsers.add_parser("add", help="Add or update an offline account")
    add_parser.add_argument("username", help="Player Minecraft username")
    add_parser.add_argument("skin", nargs="?", default="", help="Skin name or player to copy skin from (optional)")

    # List command
    subparsers.add_parser("list", help="List configured accounts")

    # Set active command
    set_parser = subparsers.add_parser("set-active", help="Set the active account")
    set_parser.add_argument("account", help="Username or account ID")

    # Delete / Remove commands
    for cmd in ("delete", "remove", "rm"):
        del_parser = subparsers.add_parser(cmd, help="Delete an account (or --all to remove all)")
        del_parser.add_argument("account", nargs="?", default="", help="Username or account ID to delete (interactive if omitted)")
        del_parser.add_argument("--all", "-a", action="store_true", help="Remove all accounts")

    # Patch command
    patch_parser = subparsers.add_parser("patch", help="Patch Lunar Client for offline play")
    patch_parser.add_argument("--target", "-t", help="Path to app.asar (Windows) or Lunar_Client.AppImage (Linux)")
    patch_parser.add_argument("--appimage", "-a", help=argparse.SUPPRESS)

    # Launch command
    launch_parser = subparsers.add_parser("launch", help="Launch Lunar Client")
    launch_parser.add_argument("--target", "-t", help="Path to executable or AppImage")
    launch_parser.add_argument("--appimage", "-a", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if not args.command or args.command == "gui":
        if IS_WINDOWS or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            run_gui()
        else:
            run_interactive_cli()
    elif args.command in ("menu", "cli", "interactive"):
        run_interactive_cli()
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
    elif args.command in ("delete", "remove", "rm"):
        if args.all:
            delete_all_accounts()
            print("[✓] All offline accounts have been removed.")
        elif args.account:
            username = delete_account(args.account)
            print(f"[✓] Deleted account '{username}'.")
        else:
            # Interactive prompt if no account argument was passed
            data = load_accounts(auto_refresh=False)
            accounts = data.get("accounts", {})
            if not accounts:
                print("[i] No configured accounts found.")
                return
            acc_items = list(accounts.items())
            print("\nConfigured Accounts:")
            for idx, (lid, acc) in enumerate(acc_items, start=1):
                active_mark = " [ACTIVE]" if lid == data.get("activeAccountLocalId") else ""
                print(f"  {idx}. {acc.get('username')}{active_mark} (ID: {lid})")
            print(f"  {len(acc_items) + 1}. Remove ALL accounts")
            print(f"  0. Cancel")
            try:
                choice = input(f"\nPlease enter an option to delete (0-{len(acc_items) + 1}): ").strip()
                if choice in ("0", "cancel", "c", ""):
                    print("Cancelled.")
                    return
                c_int = int(choice)
                if 1 <= c_int <= len(acc_items):
                    target_lid, target_acc = acc_items[c_int - 1]
                    username = delete_account(target_lid)
                    print(f"[✓] Deleted account '{username}'.")
                elif c_int == len(acc_items) + 1:
                    delete_all_accounts()
                    print("[✓] All offline accounts have been removed.")
                else:
                    print("[!] Invalid option.")
            except (ValueError, EOFError, KeyboardInterrupt):
                print("\nCancelled.")
    elif args.command == "patch":
        target_arg = getattr(args, "target", None) or getattr(args, "appimage", None)
        target = find_target(target_arg)
        print(f"[*] Target: {target}")
        patch_target(target)
    elif args.command == "launch":
        target_arg = getattr(args, "target", None) or getattr(args, "appimage", None)
        target = Path(target_arg) if target_arg else None
        launch_lunar_client(target)


if __name__ == "__main__":
    main()
