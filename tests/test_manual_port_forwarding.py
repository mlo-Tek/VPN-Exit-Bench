import unittest

from port_forwarding import normalize_manual_forward_result


class ManualPortForwardingTests(unittest.TestCase):
    def test_open_manual_port_stays_open(self):
        result = normalize_manual_forward_result(
            {"status": "open", "verified": True, "tcp_open": True},
            51926,
        )
        self.assertEqual(result["status"], "open")
        self.assertTrue(result["configured"])
        self.assertTrue(result["verified"])
        self.assertEqual(result["public_port"], 51926)

    def test_closed_exit_probe_becomes_mapped_unverified(self):
        result = normalize_manual_forward_result(
            {"status": "closed", "verified": True, "tcp_open": False},
            51926,
        )
        self.assertEqual(result["status"], "mapped_unverified")
        self.assertTrue(result["configured"])
        self.assertFalse(result["verified"])
        self.assertIsNone(result["tcp_open"])
        self.assertTrue(result["exit_ip_check_verified"])
        self.assertFalse(result["exit_ip_tcp_open"])
        self.assertEqual(result["verification_scope"], "current_exit_ip")

    def test_unavailable_external_probe_is_still_configured(self):
        result = normalize_manual_forward_result(
            {"status": "unknown", "verified": False, "tcp_open": None},
            51926,
        )
        self.assertEqual(result["status"], "mapped_unverified")
        self.assertTrue(result["configured"])
        self.assertFalse(result["verified"])

    def test_no_manual_port_keeps_original_status(self):
        original = {"status": "unknown", "verified": False}
        self.assertEqual(normalize_manual_forward_result(original, 0), original)


if __name__ == "__main__":
    unittest.main()
