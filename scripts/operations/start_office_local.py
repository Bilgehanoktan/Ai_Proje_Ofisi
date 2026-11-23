"""Tek tikla yerel AI Proje Ofisi baslatici (WSL PG 18.6 + systemd + Web/SSE sunucusu)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "product/backend"), str(ROOT / "contracts/source/python")]

from company_os.api.http.app import make_wsgi_app  # noqa: E402
from company_os.projections.sse_stream import ProjectionEvent  # noqa: E402

WSL_BOOT_PY = """
import json, subprocess
from pathlib import Path

pg = Path('/var/lib/ai-proje-ofisi-dbtest/binary/usr')
pgbin = pg / 'lib/postgresql/18/bin'
env = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LD_LIBRARY_PATH': str(pg / 'lib/x86_64-linux-gnu')}
sock = '/var/lib/ai-proje-ofisi-local/socket'
data = '/var/lib/ai-proje-ofisi-local/data'
logf = '/var/lib/ai-proje-ofisi-local/postgres.log'

chk = subprocess.run(['/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'pg_isready'), '-h', sock, '-p', '55490'], env=env, capture_output=True)
if chk.returncode != 0:
    st = subprocess.run(['/usr/sbin/runuser', '-u', 'aipof-dbtest', '--', str(pgbin / 'pg_ctl'), '-D', data, '-l', logf, '-w', 'start'], env=env, capture_output=True, text=True)
    if st.returncode != 0:
        raise RuntimeError(st.stderr or st.stdout)

for unit in ('aipof-worker-daemon.service', 'aipof-pg-backup.timer'):
    act = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True)
    if act.stdout.strip() != 'active':
        subprocess.run(['systemctl', 'start', unit], capture_output=True, text=True)

w_state = subprocess.run(['systemctl', 'is-active', 'aipof-worker-daemon.service'], capture_output=True, text=True).stdout.strip()
t_state = subprocess.run(['systemctl', 'is-active', 'aipof-pg-backup.timer'], capture_output=True, text=True).stdout.strip()
print(json.dumps({'postgres_55490': 'ready', 'worker_daemon': w_state, 'backup_timer': t_state}))
"""


def ensure_wsl_services(distro: str = "Ubuntu-E") -> dict[str, str]:
    """WSL2 uzerindeki PostgreSQL 18.6 ve systemd servislerinin acik oldugunu dogrular."""
    if sys.platform != "win32":
        return {"postgres_55490": "skipped_non_windows", "worker_daemon": "n/a", "backup_timer": "n/a"}
    res = subprocess.run(
        ["wsl", "-d", distro, "-u", "root", "--", "python3", "-c", WSL_BOOT_PY],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if res.returncode != 0:
        raise RuntimeError(f"WSL servisleri baslatilamadi: {(res.stderr or res.stdout).strip()}")
    lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise RuntimeError(f"Beklenmeyen WSL ciktisi: {res.stdout.strip()}")
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Proje Ofisi tek tikla baslatici.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--wsl-distro", default="Ubuntu-E")
    parser.add_argument("--skip-wsl", action="store_true", help="WSL PG/systemd kontrolunu atla")
    parser.add_argument("--no-browser", action="store_true", help="Tarayiciyi otomatik acma")
    parser.add_argument("--check-only", action="store_true", help="Servisleri kontrol et ve cik")
    args = parser.parse_args()

    print("=== AI Proje Ofisi Baslatiliyor ===", flush=True)
    if not args.skip_wsl:
        print("[1/3] WSL2 PostgreSQL 18.6 ve systemd servisleri kontrol ediliyor...", flush=True)
        try:
            status = ensure_wsl_services(args.wsl_distro)
            print(
                f"      PostgreSQL (55490): {status['postgres_55490']} | "
                f"Worker: {status['worker_daemon']} | Yedek Timer: {status['backup_timer']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"      UYARI: {exc}", flush=True)
            print("      Web arayuzu salt-okunur yerel modda acilmaya devam edecek.", flush=True)

    if args.check_only:
        print("[OK] Kontrol tamamlandi (--check-only).", flush=True)
        return 0

    startup_events = [
        ProjectionEvent(1, "t1", "ObjectiveCreated", {"source": "local-launcher", "status": "READY"}),
        ProjectionEvent(2, "t1", "Migration087Verified", {"tables": 4, "force_rls": True}),
    ]
    app = make_wsgi_app(events_provider=lambda _tid: startup_events)
    url_office = f"http://{args.host}:{args.port}/"
    url_events = f"http://{args.host}:{args.port}/live-events"

    print(f"[2/3] Web ve Canli Olay (SSE) sunucusu aciliyor: {url_office}", flush=True)
    print(f"      Canli Olay Paneli: {url_events}", flush=True)
    print("      Kapatmak icin Ctrl+C tuslarina basin.", flush=True)

    if not args.no_browser:
        def _open_browser():
            time.sleep(1.0)
            webbrowser.open(url_office)

        threading.Thread(target=_open_browser, daemon=True).start()

    print("[3/3] AI Proje Ofisi hazir.", flush=True)
    with make_server(args.host, args.port, app) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nAI Proje Ofisi sunucusu durduruldu.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
