import tempfile
import unittest
from pathlib import Path

from auth import check, token_hash


class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "token.sha256"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fails_closed_without_hash_file(self):
        self.assertEqual(check("anything", self.path)[0], 503)

    def test_fails_closed_with_empty_hash_file(self):
        self.path.write_text("\n")
        self.assertEqual(check("anything", self.path)[0], 503)

    def test_missing_header(self):
        self.path.write_text(token_hash("s3cret") + "\n")
        self.assertEqual(check(None, self.path)[0], 401)
        self.assertEqual(check("", self.path)[0], 401)

    def test_wrong_token(self):
        self.path.write_text(token_hash("s3cret") + "\n")
        self.assertEqual(check("nope", self.path)[0], 403)

    def test_right_token(self):
        self.path.write_text(token_hash("s3cret") + "\n")
        self.assertIsNone(check("s3cret", self.path))


if __name__ == "__main__":
    unittest.main()
