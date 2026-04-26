"""
server.py – Multi-threaded HTTP/1.1 Web Server (raw sockets, no HTTPServer)
============================================================================
Usage:
    python server.py [--host HOST] [--port PORT]

Defaults: host=127.0.0.1, port=8080
"""

import socket
import threading
import logging
import datetime
import argparse
import os

from http_handlers import build_response

# ---------------------------------------------------------------------------
# Logging setup – one rotating log file, one console handler
# ---------------------------------------------------------------------------
LOG_FILE = "server.log"

logger = logging.getLogger("WebServer")
logger.setLevel(logging.DEBUG)

# File handler: records every request
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
)

# Console handler: shows activity on screen
_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.DEBUG)
_console_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
)

logger.addHandler(_file_handler)
logger.addHandler(_console_handler)


# ---------------------------------------------------------------------------
# Request reader helper
# ---------------------------------------------------------------------------

RECV_BUFFER = 4096           # bytes per recv() call
KEEP_ALIVE_TIMEOUT = 15      # seconds to wait for next request on kept-alive conn
MAX_REQUEST_SIZE = 8192      # maximum header size in bytes


def _recv_request(conn: socket.socket, timeout: float) -> str | None:
    """
    Read one complete HTTP request (headers only) from *conn*.

    Returns the raw request string, or None if the connection was closed /
    timed out before a full request arrived.
    """
    conn.settimeout(timeout)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(RECV_BUFFER)
            if not chunk:           # client closed connection
                return None
            data += chunk
            if len(data) > MAX_REQUEST_SIZE:
                break               # treat oversized header as 400 later
    except socket.timeout:
        return None
    except OSError:
        return None
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Per-connection handler (runs in its own thread)
# ---------------------------------------------------------------------------

def _handle_connection(conn: socket.socket, client_addr: tuple) -> None:
    """
    Handle one TCP connection.  A keep-alive connection loops here until
    the client closes it or the timeout fires.
    """
    client_ip = client_addr[0]
    logger.debug("New connection from %s", client_ip)

    keep_alive = True           # optimistic; corrected after first parse

    while keep_alive:
        # Use KEEP_ALIVE_TIMEOUT for subsequent requests;
        # the first request also uses it (browsers connect fast).
        raw_request = _recv_request(conn, KEEP_ALIVE_TIMEOUT)

        if raw_request is None:
            logger.debug("Connection from %s closed / timed out", client_ip)
            break

        # Blank / whitespace-only data
        if not raw_request.strip():
            break

        # Delegate all HTTP logic to http_handlers
        response_bytes, requested_file, status_code, keep_alive = build_response(
            raw_request
        )

        # Log: client_ip | timestamp | file | status
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "%-15s | %s | %-30s | %s",
            client_ip,
            timestamp,
            requested_file,
            status_code,
        )

        try:
            conn.sendall(response_bytes)
        except OSError as exc:
            logger.warning("Send error to %s: %s", client_ip, exc)
            break

        # If the handler says close, stop the loop
        if not keep_alive:
            break

    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.close()
    logger.debug("Connection from %s closed cleanly", client_ip)


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------

def run_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    """
    Create a TCP socket, bind, listen, and accept connections forever.
    Each accepted connection is handed to a daemon thread.
    """
    # Create the listening socket
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow quick restart without "Address already in use"
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_sock.bind((host, port))
    server_sock.listen(128)          # backlog: up to 128 queued connections

    logger.info("=" * 60)
    logger.info("  HTTP Server started on http://%s:%d", host, port)
    logger.info("  Serving files from: %s", os.path.join(os.getcwd(), "htdocs"))
    logger.info("  Log file: %s", os.path.abspath(LOG_FILE))
    logger.info("  Press Ctrl+C to stop.")
    logger.info("=" * 60)

    try:
        while True:
            try:
                conn, client_addr = server_sock.accept()
            except KeyboardInterrupt:
                raise               # propagate to outer handler
            except OSError as exc:
                logger.error("Accept error: %s", exc)
                continue

            # Spawn a daemon thread so the server can exit cleanly on Ctrl+C
            thread = threading.Thread(
                target=_handle_connection,
                args=(conn, client_addr),
                daemon=True,
            )
            thread.start()
            logger.debug(
                "Active threads (excl. main): %d",
                threading.active_count() - 1,
            )

    except KeyboardInterrupt:
        logger.info("Shutting down server…")
    finally:
        server_sock.close()
        logger.info("Server socket closed. Goodbye!")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple multi-threaded HTTP server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port number (default: 8080)")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port)