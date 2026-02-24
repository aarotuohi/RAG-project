"""
AISALES — Desktop launcher.
Starts the FastAPI backend in a background thread, then opens PyWebView.
"""
import threading
import time
import sys
import uvicorn
import webview

BACKEND_PORT = 8765
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"


def _start_backend():
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=BACKEND_PORT,
        log_level="warning",
    )


def main():
    # Start backend 
    thread = threading.Thread(target=_start_backend, daemon=True)
    thread.start()

    # Wait for backend to be ready
    import requests
    for _ in range(30):
        try:
            r = requests.get(f"{BACKEND_URL}/api/status", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)

    # Open PyWebView window
    window = webview.create_window(
        title="AISALES",
        url=BACKEND_URL,
        width=1280,
        height=860,
        min_size=(900, 600),
        resizable=True,
    )
    webview.start(debug="--debug" in sys.argv)


if __name__ == "__main__":
    main()
