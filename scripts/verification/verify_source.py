"""Yerel kaynak kontrolleri; DB, servis veya model başlatmaz."""
from pathlib import Path
import sys
import unittest

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'docs/migration/SOURCE_TO_TARGET.json').is_file())


def main():
    sys.path[:0] = [str(ROOT), str(ROOT/'product/backend'), str(ROOT/'contracts/source/python'), str(ROOT/'verifier/src')]
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / 'tests'), pattern='test_*.py', top_level_dir=str(ROOT)
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if (ROOT/'SOURCE_MANIFEST.json').exists():
        from scripts.verification.verify_layout import verify
        import json
        layout = verify()
        print(json.dumps(layout, ensure_ascii=False))
        if layout['status'] != 'PASS':
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
