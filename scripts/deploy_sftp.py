#!/usr/bin/env python3
"""Deploy the built site over SFTP, mirroring an interactive `sftp` login.

Replicates what works manually (`sftp -P 22 user@host`):
  1. password auth
  2. keyboard-interactive auth (answering prompts with the same password)
IONOS shared hosting sometimes requires the second path, which off-the-shelf
password-SFTP actions don't implement.

Env vars (from GitHub Actions secrets):
  SFTP_HOST, SFTP_USER, SFTP_PASSWORD  required
  SFTP_PORT                            optional, default 22
  SFTP_REMOTE_DIR                      optional, default ./
  SFTP_LOCAL_DIR                       optional, default dist
"""

import os
import posixpath
import sys
from pathlib import Path

import paramiko


def clean(value: str) -> str:
    """Strip whitespace/newlines/quotes that sneak into pasted secrets."""
    return value.strip().strip("'\"")


HOST = clean(os.environ.get("SFTP_HOST", ""))
USER = clean(os.environ.get("SFTP_USER", ""))
PASSWORD = os.environ.get("SFTP_PASSWORD", "")
PORT = int(clean(os.environ.get("SFTP_PORT", "22")) or 22)
REMOTE_DIR = clean(os.environ.get("SFTP_REMOTE_DIR", "./")) or "./"
LOCAL_DIR = Path(clean(os.environ.get("SFTP_LOCAL_DIR", "dist")) or "dist")

if not (HOST and USER and PASSWORD):
    sys.exit("Missing SFTP_HOST / SFTP_USER / SFTP_PASSWORD env vars")


def connect_transport() -> paramiko.Transport:
    """Open the SSH transport WITHOUT authenticating, so we control auth."""
    transport = paramiko.Transport((HOST, PORT))
    transport.start_client(timeout=30)
    if not transport.is_active():
        sys.exit(f"Could not establish SSH transport to {HOST}:{PORT}")
    return transport


def authenticate(transport: paramiko.Transport) -> str:
    """Try password auth, then keyboard-interactive (like interactive sftp)."""
    try:
        transport.auth_password(USER, PASSWORD, fallback=False)
        return "password"
    except paramiko.AuthenticationException:
        print("password auth rejected; trying keyboard-interactive", flush=True)
    except paramiko.SSHException as exc:
        print(f"password auth unavailable ({exc}); trying keyboard-interactive", flush=True)

    def handler(title, instructions, prompts):
        print(
            f"  keyboard-interactive: title={title!r} prompts={[p[0] for p in prompts]}",
            flush=True,
        )
        return [PASSWORD] * len(prompts)

    try:
        transport.auth_interactive(USER, handler)
        return "keyboard-interactive"
    except paramiko.SSHException:
        raise
    except Exception as exc:  # keep the traceback readable in CI logs
        raise paramiko.AuthenticationException(f"interactive auth failed: {exc}") from exc


def upload(transport: paramiko.Transport) -> None:
    if not LOCAL_DIR.is_dir():
        sys.exit(f"Local build dir not found: {LOCAL_DIR.resolve()}")

    files = [p for p in LOCAL_DIR.rglob("*") if p.is_file()]
    print(f"Deploying {len(files)} files from {LOCAL_DIR}/ to {USER}@{HOST}:{REMOTE_DIR}", flush=True)

    sftp = paramiko.SFTPClient.from_transport(transport)
    assert sftp is not None, "SFTP session could not be opened"
    remote_base = posixpath.normpath(REMOTE_DIR)
    uploaded = 0

    for path in files:
        rel = path.relative_to(LOCAL_DIR).as_posix()
        remote_path = posixpath.join(remote_base, rel)

        # mkdir -p for every parent segment
        parent = posixpath.dirname(remote_path)
        stack = []
        probe = parent
        while probe and probe not in ("/", "."):
            try:
                sftp.stat(probe)
                break
            except FileNotFoundError:
                stack.append(probe)
                probe = posixpath.dirname(probe)
        for directory in reversed(stack):
            print(f"  mkdir {directory}", flush=True)
            sftp.mkdir(directory)

        sftp.put(str(path), remote_path)
        uploaded += 1
        if uploaded % 25 == 0:
            print(f"  {uploaded}/{len(files)} uploaded", flush=True)

    print(f"Uploaded {uploaded}/{len(files)} files", flush=True)

    # sanity check: index.html exists at the root we uploaded to
    try:
        st = sftp.stat(posixpath.join(remote_base, "index.html"))
        print(f"Verified index.html on server ({st.st_size} bytes)", flush=True)
    except FileNotFoundError:
        print("WARNING: index.html not found at remote root after upload", flush=True)

    sftp.close()


def main() -> None:
    transport = connect_transport()
    try:
        method = authenticate(transport)
        print(f"Authenticated via {method}", flush=True)
        upload(transport)
    finally:
        transport.close()
    print("Deploy complete.", flush=True)


if __name__ == "__main__":
    main()
