import os
import sys
import json
import struct
import tempfile
import unittest
from pathlib import Path

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))
import lunar_offline_manager as lom

class TestLunarOfflineEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.tmp_dir.name)
        # Mock paths
        lom.GAME_SETTINGS_DIR = self.test_dir / "settings" / "game"
        lom.ACCOUNTS_FILE = lom.GAME_SETTINGS_DIR / "accounts.json"
        lom.SAVED_SKINS_FILE = lom.GAME_SETTINGS_DIR / "saved_skins.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_account_creation_and_lifecycle(self):
        # 1. Add account
        acc = lom.add_offline_account("TestGamer", "Technoblade")
        self.assertEqual(acc["username"], "TestGamer")
        self.assertTrue(acc["accessToken"].startswith("offline_token_"))
        self.assertTrue(acc["refreshToken"].startswith("offline_refresh_"))
        self.assertEqual(acc["type"], "Xbox")

        # 2. Check accounts.json
        data = lom.load_accounts(auto_refresh=False)
        self.assertEqual(data["activeAccountLocalId"], acc["localId"])
        self.assertIn(acc["localId"], data["accounts"])

        # 3. Add second account
        acc2 = lom.add_offline_account("PlayerTwo", "Steve")
        data = lom.load_accounts(auto_refresh=False)
        self.assertEqual(len(data["accounts"]), 2)
        self.assertEqual(data["activeAccountLocalId"], acc2["localId"])

        # 4. Set active account back to first
        lom.set_active_account("TestGamer")
        data = lom.load_accounts(auto_refresh=False)
        self.assertEqual(data["activeAccountLocalId"], acc["localId"])

        # 5. Delete second account
        lom.delete_account("PlayerTwo")
        data = lom.load_accounts(auto_refresh=False)
        self.assertEqual(len(data["accounts"]), 1)
        self.assertEqual(data["activeAccountLocalId"], acc["localId"])

        # 6. Delete all accounts
        lom.delete_all_accounts()
        data = lom.load_accounts(auto_refresh=False)
        self.assertEqual(len(data["accounts"]), 0)
        self.assertIsNone(data["activeAccountLocalId"])

    def test_windows_asar_patching(self):
        # Create a mock ASAR file containing electron/main.js
        sample_main_js = (
            'console.log("Starting Lunar Client");\n'
            'const profile = { invalid:!e.refreshToken };\n'
            'try{nV.info(`Validating account ${r.minecraftProfile.name} owns Minecraft...`);}\n'
            'XV=async(e,t)=>{if(!e)throw new zB(WB.NO_ACCOUNT,`No account found for getting Lunar Client Token`);}\n'
            'async refreshAccountInternal(e){if(!e.refreshToken)throw new zB(WB.INVALID_SESSION,\n'
        ).encode("utf-8")

        mock_header = {
            "files": {
                "dist-electron": {
                    "files": {
                        "electron": {
                            "files": {
                                "main.js": {
                                    "size": len(sample_main_js),
                                    "offset": "0"
                                }
                            }
                        }
                    }
                }
            }
        }
        header_json = json.dumps(mock_header, separators=(",", ":")).encode("utf-8")
        pad = (4 - (len(header_json) % 4)) % 4
        if pad:
            header_json += b" " * pad
        j_len = len(header_json)

        asar_file = self.test_dir / "app.asar"
        with open(asar_file, "wb") as f:
            f.write(struct.pack("<IIII", 4, j_len + 8, j_len + 4, j_len))
            f.write(header_json)
            f.write(sample_main_js)

        # Apply Windows ASAR patch
        lom.patch_windows_asar(asar_file)

        # Verify backup was created
        self.assertTrue((self.test_dir / "app.asar.bak").is_file())

        # Inspect patched main.js
        with open(asar_file, "rb") as f:
            h_raw = f.read(16)
            magic, s1, s2, j_size = struct.unpack("<IIII", h_raw)
            header = json.loads(f.read(j_size).decode("utf-8"))
            p_base = f.tell()
            node = header["files"]["dist-electron"]["files"]["electron"]["files"]["main.js"]
            f.seek(p_base + int(node["offset"]))
            patched_content = f.read(int(node["size"])).decode("utf-8")

        self.assertIn("[Offline] Account", patched_content)
        self.assertIn("refreshed locally", patched_content)
        self.assertIn("offline-jwt", patched_content)
        self.assertIn("!e.accessToken?.startsWith(`offline`)", patched_content)

        # Test idempotency (patching again shouldn't fail or corrupt)
        lom.patch_windows_asar(asar_file)

if __name__ == "__main__":
    unittest.main()
