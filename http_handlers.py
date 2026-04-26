import os
import datetime
import pathlib

# ---------- constants ----------
STATUS_LINES = {
    200: 'HTTP/1.1 200 OK\r\n',
    304: 'HTTP/1.1 304 Not Modified\r\n',
    400: 'HTTP/1.1 400 Bad Request\r\n',
    403: 'HTTP/1.1 403 Forbidden\r\n',
    404: 'HTTP/1.1 404 Not Found\r\n',
}

CONTENT_TYPES = {
    '.html': 'Content-Type: text/html\r\n',
    '.png':  'Content-Type: image/png\r\n',
    '.jpg':  'Content-Type: image/jpeg\r\n',
    '.jpeg': 'Content-Type: image/jpeg\r\n',
}

ROOT_DIR = os.path.join(str(pathlib.Path().resolve()), 'htdocs')
ERROR_PAGES = {
    400: os.path.join(ROOT_DIR, '400.html'),
    403: os.path.join(ROOT_DIR, '403.html'),
    404: os.path.join(ROOT_DIR, '404.html'),
}

# ---------- helper functions ----------
def get_http_date(utc_date: datetime.datetime) -> str:
    weekday = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][utc_date.weekday()]
    month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][utc_date.month - 1]
    return f"{weekday}, {utc_date.day:02d} {month} {utc_date.year} {utc_date.hour:02d}:{utc_date.minute:02d}:{utc_date.second:02d} GMT"

def parse_request_head(request_str: str):
    """Returns (method, url, protocol, headers_dict)"""
    lines = request_str.strip().split('\r\n')
    method_line = lines[0].split(' ')
    method = method_line[0].upper()
    url = method_line[1]
    protocol = method_line[2] if len(method_line) > 2 else 'HTTP/1.1'
    headers = {}
    for line in lines[1:]:
        if ': ' in line:
            key, val = line.split(': ', 1)
            headers[key.lower()] = val
    return method, url, protocol, headers

def determine_keep_alive(protocol: str, headers: dict) -> bool:
    """Return True if connection should be kept alive after this response."""
    conn_header = headers.get('connection', '').lower()
    if protocol == 'HTTP/1.1':
        # default persistent unless Connection: close
        return conn_header != 'close'
    else:  # HTTP/1.0
        return conn_header == 'keep-alive'

def serve_error_page(code: int) -> tuple:
    """Returns (status_line, headers_str, body_bytes) for given error code."""
    status_line = STATUS_LINES.get(code, STATUS_LINES[404])
    body = b''
    headers = f'Date: {get_http_date(datetime.datetime.utcnow())}\r\n'
    error_file = ERROR_PAGES.get(code)
    if error_file and os.path.isfile(error_file):
        with open(error_file, 'rb') as f:
            body = f.read()
        headers += CONTENT_TYPES['.html']
    else:
        body = f"<html><body><h1>{code} Error</h1></body></html>".encode()
        headers += CONTENT_TYPES['.html']
    headers += f'Content-Length: {len(body)}\r\n'
    return status_line, headers, body

def build_response(request_str: str) -> (bytes, str, bool):
    """
    Returns:
        response_bytes : bytes  - full HTTP response
        requested_file : str   - for logging
        response_code  : str   - status code as string
        keep_alive     : bool  - whether to keep connection open
    """
    try:
        method, url, protocol, headers = parse_request_head(request_str)
    except Exception:
        # Malformed request -> 400
        status_line, hdrs, body = serve_error_page(400)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, 'unknown', '400', False

    keep_alive = determine_keep_alive(protocol, headers)

    # Only GET and HEAD are supported
    if method not in ('GET', 'HEAD'):
        status_line, hdrs, body = serve_error_page(400)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, url.strip('/'), '400', keep_alive

    # Build file path
    if url == '/':
        rel_path = '/index.html'
    else:
        rel_path = url

    # ── Security Guard 1: raw URL segment check ──────────────────────────────
    # Reject BEFORE normpath if any path segment is '..'.
    # This catches traversal attempts sent literally by crafted clients or
    # raw-socket tests (curl --path-as-is, netcat, etc.).
    # Note: regular browsers and curl normalise URLs client-side first, so
    # they never send '..' to the server — but we must still handle it here.
    url_segments = rel_path.replace('\\', '/').split('/')
    if '..' in url_segments:
        status_line, hdrs, body = serve_error_page(403)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, rel_path.lstrip('/'), '403', keep_alive

    file_path = os.path.normpath(ROOT_DIR + rel_path)

    # ── Security Guard 2: resolved path must sit inside ROOT_DIR ─────────────
    # Append os.sep so that a sibling directory named 'htdocs_evil' (which
    # would wrongly pass a plain startswith(ROOT_DIR) check) is rejected.
    inside_root = (file_path == ROOT_DIR or
                   file_path.startswith(ROOT_DIR + os.sep))
    if not inside_root:
        status_line, hdrs, body = serve_error_page(403)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, rel_path.lstrip('/'), '403', keep_alive

    requested_file = rel_path.lstrip('/') if rel_path != '/' else 'index.html'

    # Check existence and permissions
    if not os.path.exists(file_path):
        status_line, hdrs, body = serve_error_page(404)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, requested_file, '404', keep_alive

    if not os.access(file_path, os.R_OK):
        status_line, hdrs, body = serve_error_page(403)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, requested_file, '403', keep_alive

    # If it's a directory, try index.html inside
    if os.path.isdir(file_path):
        file_path = os.path.join(file_path, 'index.html')
        if not os.path.isfile(file_path):
            status_line, hdrs, body = serve_error_page(404)
            full_resp = (status_line + hdrs + '\r\n').encode() + body
            return full_resp, requested_file, '404', keep_alive

    # Get last-modified time
    mtime = os.path.getmtime(file_path)
    last_modified = get_http_date(datetime.datetime.utcfromtimestamp(mtime))

    # Prepare headers (Date + Last-Modified + Connection)
    resp_headers = f'Date: {get_http_date(datetime.datetime.utcnow())}\r\n'
    resp_headers += f'Last-Modified: {last_modified}\r\n'
    if keep_alive:
        resp_headers += 'Connection: keep-alive\r\nKeep-Alive: timeout=15\r\n'
    else:
        resp_headers += 'Connection: close\r\n'

    # Check If-Modified-Since
    if 'if-modified-since' in headers:
        try:
            since_str = headers['if-modified-since']
            since_dt = datetime.datetime.strptime(since_str, '%a, %d %b %Y %H:%M:%S %Z')
            since_ts = since_dt.timestamp()
            if since_ts >= mtime - 1:   # 1 second tolerance
                # 304 Not Modified - no body
                status_line = STATUS_LINES[304]
                minimal_headers = f'Date: {get_http_date(datetime.datetime.utcnow())}\r\n'
                minimal_headers += f'Last-Modified: {last_modified}\r\n'
                if keep_alive:
                    minimal_headers += 'Connection: keep-alive\r\n'
                else:
                    minimal_headers += 'Connection: close\r\n'
                full_resp = (status_line + minimal_headers + '\r\n').encode()
                return full_resp, requested_file, '304', keep_alive
        except Exception:
            pass   # malformed date, ignore

    # Determine content type and read file
    ext = os.path.splitext(file_path)[1].lower()
    ctype = CONTENT_TYPES.get(ext, CONTENT_TYPES['.html'])
    resp_headers += ctype

    try:
        if ext in ('.png', '.jpg', '.jpeg'):
            with open(file_path, 'rb') as f:
                body = f.read()
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                body = f.read().encode('utf-8')
    except Exception:
        status_line, hdrs, body = serve_error_page(404)
        full_resp = (status_line + hdrs + '\r\n').encode() + body
        return full_resp, requested_file, '404', keep_alive

    # Content-Length is always based on the real body size (even for HEAD)
    resp_headers += f'Content-Length: {len(body)}\r\n'

    # If HEAD method: discard body (Content-Length header still reflects real size)
    if method == 'HEAD':
        body = b''

    status_line = STATUS_LINES[200]
    full_resp = (status_line + resp_headers + '\r\n').encode() + body
    return full_resp, requested_file, '200', keep_alive