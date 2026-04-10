import unittest

import vless_manager


class LegacyVlessContractTests(unittest.TestCase):
    def test_build_legacy_vless_contract_keeps_required_fields(self):
        config = {
            "server": "203.0.113.10",
            "port": 443,
            "uuid": "11111111-2222-3333-4444-555555555555",
            "public_key": "examplePublicKeyValue",
            "short_id": "6ba85179e30d4fc2",
            "sni": "www.microsoft.com",
            "fingerprint": "chrome",
            "flow": "xtls-rprx-vision",
            "private_key": "server-only-secret",
        }

        legacy = vless_manager.build_legacy_vless_contract(config)
        is_valid, missing = vless_manager.validate_legacy_vless_contract(legacy)

        self.assertTrue(is_valid, f"missing fields: {missing}")
        self.assertEqual(
            tuple(legacy.keys()),
            vless_manager.LEGACY_VLESS_REQUIRED_FIELDS,
        )
        self.assertNotIn("private_key", legacy)

    def test_validate_legacy_vless_contract_reports_missing_fields(self):
        legacy = {
            "server": "203.0.113.10",
            "port": 443,
            "uuid": "",
            "public_key": "examplePublicKeyValue",
            "short_id": "",
            "sni": "www.microsoft.com",
            "fingerprint": "chrome",
            "flow": "xtls-rprx-vision",
        }

        is_valid, missing = vless_manager.validate_legacy_vless_contract(legacy)

        self.assertFalse(is_valid)
        self.assertEqual(missing, ["uuid", "short_id"])


if __name__ == "__main__":
    unittest.main()
