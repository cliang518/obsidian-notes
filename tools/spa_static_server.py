from __future__ import annotations

import argparse
import mimetypes
from http.client import HTTPConnection
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


class SpaStaticHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args,
        directory: str | None = None,
        api_target_host: str = "127.0.0.1",
        api_target_port: int = 8011,
        **kwargs,
    ):
        self._root_directory = Path(directory or ".").resolve()
        self._api_target_host = api_target_host
        self._api_target_port = api_target_port
        super().__init__(*args, directory=str(self._root_directory), **kwargs)

    def log_message(self, format: str, *args: object) -> None:
        # The tray starts this server through pythonw.exe, where stderr may not
        # exist. SimpleHTTPRequestHandler writes access logs to stderr by
        # default; in a windowless process that can abort large asset requests
        # with "Empty reply from server". Keep the background service quiet and
        # stable.
        return

    def end_headers(self) -> None:
        if self.path in ("/", "/index.html") or not Path(urlparse(self.path).path).suffix:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _apply_spa_fallback(self) -> bool:
        parsed = urlparse(self.path)
        raw_path = unquote(parsed.path or "/")
        request_path = raw_path.lstrip("/") or "index.html"
        candidate = (self._root_directory / request_path).resolve()

        if candidate.exists() and candidate.is_file():
            return True

        # Assets keep 404 semantics, while application routes fall back to index.html.
        if Path(raw_path).suffix:
            self.send_error(404, "File not found")
            return False

        self.path = "/index.html"
        return True

    def do_GET(self) -> None:
        if self._proxy_api():
            return
        if not self._apply_spa_fallback():
            return
        return super().do_GET()

    def do_HEAD(self) -> None:
        if self._proxy_api():
            return
        if not self._apply_spa_fallback():
            return
        return super().do_HEAD()

    def guess_type(self, path: str) -> str:
        guessed = super().guess_type(path)
        if guessed == "application/octet-stream":
            alt, _ = mimetypes.guess_type(path)
            if alt:
                return alt
        return guessed

    def _proxy_api(self) -> bool:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            return False

        content_length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(content_length) if content_length > 0 else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
        }
        headers["Host"] = f"{self._api_target_host}:{self._api_target_port}"

        connection = HTTPConnection(self._api_target_host, self._api_target_port, timeout=30)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()

            self.send_response(response.status, response.reason)
            excluded_headers = {
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailers",
                "upgrade",
            }
            for key, value in response.getheaders():
                if key.lower() in excluded_headers:
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
            return True
        except BrokenPipeError:
            return True
        except ConnectionResetError:
            return True
        finally:
            connection.close()

    def do_POST(self) -> None:
        if self._proxy_api():
            return
        self.send_error(501, "Unsupported method")

    def do_PUT(self) -> None:
        if self._proxy_api():
            return
        self.send_error(501, "Unsupported method")

    def do_DELETE(self) -> None:
        if self._proxy_api():
            return
        self.send_error(501, "Unsupported method")

    def do_PATCH(self) -> None:
        if self._proxy_api():
            return
        self.send_error(501, "Unsupported method")


def main() -> None:
    parser = argparse.ArgumentParser(description="Static server with SPA route fallback.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=3011)
    parser.add_argument("--dir", required=True, help="Directory to serve")
    parser.add_argument("--api-host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8011)
    args = parser.parse_args()

    handler = partial(
        SpaStaticHandler,
        directory=args.dir,
        api_target_host=args.api_host,
        api_target_port=args.api_port,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
