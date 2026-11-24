import unittest
from io import BytesIO
from wsgiref.util import setup_testing_defaults

from company_os.api.http.app import make_wsgi_app


def _call_wsgi(app, path: str, method: str = "GET") -> tuple[str, dict[str, str], bytes]:
    environ = {}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["PATH_INFO"] = path
    environ["wsgi.input"] = BytesIO(b"")
    status_box = []
    headers_box = []

    def start_response(status, headers):
        status_box.append(status)
        headers_box.append({k.lower(): v for k, v in headers})

    body = b"".join(app(environ, start_response))
    return status_box[0], headers_box[0], body


class FrontendAssetsTests(unittest.TestCase):
    def setUp(self):
        self.app = make_wsgi_app()

    def test_static_assets_serves_tokens_css_with_nosniff(self):
        status, headers, body = _call_wsgi(self.app, "/assets/tokens.css")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers.get("content-type"), "text/css; charset=utf-8")
        self.assertEqual(headers.get("x-content-type-options"), "nosniff")
        self.assertIn(b"--accent:", body)

    def test_static_assets_rejects_path_traversal_and_disallowed_extensions(self):
        for bad_path in (
            "/assets/../live-events.html",
            "/assets/../../backend/company_os/api/http/app.py",
            "/office/modules/../../backend/requirements.txt",
            "/assets/vendor/PHASER_PROVENANCE.json",
        ):
            status, _headers, _body = _call_wsgi(self.app, bad_path)
            self.assertIn(status.split()[0], ("403", "404"), bad_path)


if __name__ == "__main__":
    unittest.main()
