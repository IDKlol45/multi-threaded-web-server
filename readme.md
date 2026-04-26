# HTTP Web Server – README

A multi-threaded HTTP/1.1 web server built from scratch in Python using
raw `socket` and `threading` — **no** `HTTPServer` or third-party libraries.

---

## Requirements

| Item | Details |
|---|---|
| Python | 3.9 or later |
| OS | Windows / macOS / Linux |
| Dependencies | **None** — standard library only |

---

## File Structure

```
project/
├── server.py          # Entry-point: socket creation, threading, logging
├── http_handlers.py   # HTTP parsing and response builder
├── server.log         # Request log (auto-created on first run)
├── README.md          # This file
└── htdocs/            # Web-root directory (files served to clients)
    ├── index.html     # Home page
    ├── about.html     # About page
    ├── image.html     # Image test page
    ├── logo.png       # Sample PNG image
    ├── 400.html       # 400 Bad Request error page
    ├── 403.html       # 403 Forbidden error page
    └── 404.html       # 404 Not Found error page
```

---

## How to Run

### 1 — Clone / download the project

```bash
git clone <your-repo-url>
cd project
```

### 2 — Start the server (defaults: 127.0.0.1 port 8080)

```bash
python server.py
```

With custom host / port:

```bash
python server.py --host 0.0.0.0 --port 9090
```

### 3 — Open a browser and visit

```
http://127.0.0.1:8080/
```

### 4 — Stop the server

Press **Ctrl + C** in the terminal.

---

## Testing

### Browser

| URL | Expected result |
|---|---|
| `http://127.0.0.1:8080/` | Home page (200 OK) |
| `http://127.0.0.1:8080/about.html` | About page (200 OK) |
| `http://127.0.0.1:8080/image.html` | Page with embedded PNG (200 OK) |
| `http://127.0.0.1:8080/logo.png` | PNG image (200 OK) |
| `http://127.0.0.1:8080/missing.html` | 404 Not Found |
| `http://127.0.0.1:8080/../secret` | 403 Forbidden |

### curl (command line)

```bash
# GET request
curl -v http://127.0.0.1:8080/

# HEAD request
curl -I http://127.0.0.1:8080/

# Test keep-alive
curl -v --http1.1 -H "Connection: keep-alive" http://127.0.0.1:8080/

# Test connection close
curl -v --http1.1 -H "Connection: close" http://127.0.0.1:8080/

# Test 304 Not Modified (replace the date with a future date)
curl -v -H "If-Modified-Since: Mon, 01 Jan 2030 00:00:00 GMT" \
     http://127.0.0.1:8080/index.html

# Test 404
curl -v http://127.0.0.1:8080/missing.html
```

---

## Log File Format

Each request is logged to **`server.log`** in the format:

```
YYYY-MM-DD HH:MM:SS | CLIENT_IP        | TIMESTAMP           | FILENAME                       | STATUS
2025-04-26 14:32:01 | 127.0.0.1       | 2025-04-26 14:32:01 | index.html                    | 200
2025-04-26 14:32:05 | 127.0.0.1       | 2025-04-26 14:32:05 | logo.png                      | 200
2025-04-26 14:32:10 | 127.0.0.1       | 2025-04-26 14:32:10 | missing.html                  | 404
```

---

## Supported HTTP Features

| Feature | Details |
|---|---|
| Methods | `GET`, `HEAD` |
| Status codes | 200, 304, 400, 403, 404 |
| File types | `.html`, `.png`, `.jpg`, `.jpeg` |
| Persistent connections | `Connection: keep-alive` (default in HTTP/1.1) |
| Non-persistent connections | `Connection: close` |
| Conditional GET | `Last-Modified` + `If-Modified-Since` → 304 |
| Multi-threading | One daemon thread per TCP connection |
| Directory traversal protection | Paths outside `htdocs/` return 403 |