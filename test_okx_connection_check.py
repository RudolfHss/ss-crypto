import base64
import hashlib
import hmac
import io
import unittest
from unittest.mock import patch

from okx_connection_check import Client, CheckError, NoRedirect, main, signature

ENV = {"OKX_API_KEY": "test-key", "OKX_SECRET_KEY": "test-secret", "OKX_PASSPHRASE": "test-pass"}


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.payload


class ConnectionTests(unittest.TestCase):
    def test_signature_matches_independent_hmac_calculation(self):
        self.assertEqual(signature("Jefe", "what do ya want for nothing?", ""),
                         base64.b64encode(hmac.new(b"Jefe", b"what do ya want for nothing?GET", hashlib.sha256).digest()).decode())

    def test_missing_secrets_fail_before_network(self):
        with patch("okx_connection_check.build_opener") as opener:
            with self.assertRaises(CheckError):
                Client("eea", "demo", {})
            opener.assert_not_called()

    def test_untrusted_domain_and_mode_rejected(self):
        for region, mode in (("https://evil.example", "demo"), ("eea", "invalid")):
            with self.assertRaises(CheckError):
                Client(region, mode, ENV)

    def test_write_endpoint_is_impossible(self):
        c = Client("eea", "live", ENV)
        with patch.object(c.opener, "open") as request:
            with self.assertRaises(CheckError):
                c.get("/api/v5/trade/order", "time")
            request.assert_not_called()

    def test_demo_header_and_live_header(self):
        for mode in ("demo", "live"):
            c = Client("eea", mode, ENV)
            with patch.object(c.opener, "open", return_value=Response(b'{"code":"0","data":[{"acctLv":"1"}]}')) as request:
                c.get("/api/v5/account/config", "2026-10-26T00:00:00.000Z")
                req = request.call_args.args[0]
                headers = {k.lower(): v for k, v in req.header_items()}
                self.assertEqual(req.get_method(), "GET")
                self.assertEqual(req.full_url, "https://eea.okx.com/api/v5/account/config")
                self.assertEqual(headers.get("x-simulated-trading"), "1" if mode == "demo" else None)

    def test_public_time_has_no_credentials(self):
        c = Client("eea", "demo", ENV)
        with patch.object(c.opener, "open", return_value=Response(b'{"code":"0","data":[{"ts":"1792972800000"}]}')) as request:
            c.get("/api/v5/public/time")
            headers = str(request.call_args.args[0].header_items())
            for value in ENV.values():
                self.assertNotIn(value, headers)

    def test_redirect_rejected(self):
        with self.assertRaises(CheckError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.example")

    def test_reflected_secrets_not_logged(self):
        c = Client("eea", "demo", ENV)
        with patch.object(c.opener, "open", return_value=Response(b'{"code":"50105","msg":"test-secret test-pass"}')):
            with self.assertRaises(CheckError) as error:
                c.get("/api/v5/account/config", "time")
            self.assertIn("50105", str(error.exception))
            self.assertNotIn("test-secret", str(error.exception))
            self.assertNotIn("test-pass", str(error.exception))

    def test_check_uses_only_two_read_endpoints(self):
        c = Client("eea", "demo", ENV)
        with patch.object(c, "get", side_effect=[[{"ts":"1792972800000"}], [{"acctLv":"1", "uid":"private-id"}]]) as get:
            result = c.check()
            self.assertEqual([x.args[0] for x in get.call_args_list], ["/api/v5/public/time", "/api/v5/account/config"])
            self.assertNotIn("private-id", result)

    def test_failure_exits_nonzero(self):
        with patch.dict("os.environ", {}, clear=True), patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(main(), 1)
            self.assertIn("SIKERTELEN", output.getvalue())


if __name__ == "__main__":
    unittest.main()
