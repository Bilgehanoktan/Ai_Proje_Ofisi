"""Own and close a temporary local UI server for the moved-source browser check."""
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'product/backend'),str(ROOT/'contracts/source/python'),str(ROOT/'verifier/src')]
from company_os.api.http.task_http import create_server
from scripts.verification.check_task_screen import main as browser_check


def main():
    server=create_server(port=0)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        sys.argv=[__file__,'--port',str(server.server_port)]
        browser_check()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__=='__main__':
    main()
