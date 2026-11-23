import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from company_os.adapters.secrets.secret_adapter import read_enrolled_key, read_secret_bytes, SecretUnavailable


class SecretBoundaryTests(unittest.TestCase):
    def test_path_and_missing_owner_cannot_bypass_enrollment(self):
        with patch('pathlib.Path.read_bytes', side_effect=AssertionError('must not read')):
            for value in ('secrets', Path('secrets'), True):
                with self.assertRaises(SecretUnavailable):
                    read_secret_bytes(value, 'slot', owner_uid=999)
        with self.assertRaises(TypeError):
            read_secret_bytes(5, 'slot')

    def test_owner_zero_is_preserved_and_no_default_identity_is_invented(self):
        with patch('company_os.adapters.secrets.secret_adapter.read_enrolled_key', return_value=b'x'*32) as read:
            self.assertEqual(read_secret_bytes(5, 'slot', owner_uid=0), b'x'*32)
            read.assert_called_once_with(5, 'slot', owner_uid=0)


@unittest.skipUnless(sys.platform == 'linux', 'Linux fd/owner/mode checks')
class SecretTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.path.chmod(0o700)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.key = self.path / 'slot'
        self.key.write_bytes(b'x' * 32)
        self.key.chmod(0o400)

    def test_exact_key_is_read_without_consuming_directory(self):
        self.assertEqual(read_enrolled_key(self.fd, 'slot', owner_uid=os.getuid()), b'x' * 32)
        os.fstat(self.fd)

    def test_symlink_permissions_hardlink_and_traversal_rejected(self):
        (self.path / 'alias').symlink_to(self.key)
        for name in ('alias', '../slot'):
            with self.assertRaises(SecretUnavailable):
                read_enrolled_key(self.fd, name, owner_uid=os.getuid())
        self.key.chmod(0o644)
        with self.assertRaises(SecretUnavailable):
            read_enrolled_key(self.fd, 'slot', owner_uid=os.getuid())
        self.key.chmod(0o400)
        os.link(self.key, self.path / 'hard')
        with self.assertRaises(SecretUnavailable):
            read_enrolled_key(self.fd, 'slot', owner_uid=os.getuid())
