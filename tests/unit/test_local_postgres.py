import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.database import local_postgres as setup


class LocalPostgresTests(unittest.TestCase):
    def test_prepare_never_overwrites_existing_target(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);sentinel=base/'keep';sentinel.write_text('preserve')
            with patch.object(setup,'require_uid',return_value=SimpleNamespace(pw_uid=999,pw_gid=986)),\
                    patch.object(setup,'base_path',return_value=base),\
                    patch.object(setup,'binary_digest') as digest:
                with self.assertRaisesRegex(setup.SetupBlocked,'TARGET_EXISTS_NO_OVERWRITE'):setup.prepare()
                digest.assert_not_called()
            self.assertEqual(sentinel.read_text(),'preserve')

    def test_initialize_never_reinitializes_nonempty_data(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);(base/'data').mkdir();sentinel=base/'data/keep';sentinel.write_text('preserve')
            with patch.object(setup,'checked_layout',return_value=base),patch.object(setup,'command') as command:
                with self.assertRaisesRegex(setup.SetupBlocked,'DATA_NOT_EMPTY_NO_INITIALIZATION'):setup.initialize()
                command.assert_not_called()
            self.assertEqual(sentinel.read_text(),'preserve')

    def test_start_and_stop_require_verified_owned_instance(self):
        for action in (setup.start,setup.stop):
            with self.subTest(action=action.__name__),\
                    patch.object(setup,'checked_layout',side_effect=setup.SetupBlocked('marker mismatch')),\
                    patch.object(setup,'command') as command:
                with self.assertRaises(setup.SetupBlocked):action()
                command.assert_not_called()
