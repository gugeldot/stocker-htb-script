# stocker.py

HTB Machine Stocker script for automated LFI exploitation via HTML injection in a Chromium-based PDF generator.

## Vulnerability chain

1. **NoSQLi authentication bypass** — The login endpoint passes user input directly to a MongoDB query without sanitization. Injecting `$ne` operators bypasses authentication entirely without valid credentials.

2. **Server-Side HTML Injection → LFI** — The order API renders user-controlled `title` fields as raw HTML inside a Chromium PDF generator. Injecting an `<iframe src='file://...'>` tag causes the renderer to embed local filesystem files into the generated PDF.

## Usage

```bash
python3 stocker.py --url http://dev.stocker.htb --path /etc/passwd --open-pdf false
python3 stocker.py --url http://dev.stocker.htb --path /var/www/dev/index.js --open-pdf true
python3 stocker.py --url http://dev.stocker.htb --path /root/.ssh/id_rsa --delay 6 --open-pdf false
```

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `--url` | Target base URL | required |
| `--path` | Absolute path of file to read | required |
| `--delay` | Seconds to wait for Chromium render | `3` |
| `--open-pdf` | Auto-open PDF after download (`true/false`) | required |

## Disclaimer

For educational purposes only. Use exclusively against machines you own or have explicit permission to test.

## Requirements

- Python 3.x
- `pip install requests`
