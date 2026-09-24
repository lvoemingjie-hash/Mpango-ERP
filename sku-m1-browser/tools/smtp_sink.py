#!/usr/bin/env python3
"""Local SMTP sink for the SKU browser harness (B1).

Task contract: "SMTP remains local fake/maildir only; no production email or
mailbox access." This sink accepts any mail on 127.0.0.1:<port> and files each
message into a Maildir (results/maildir/{tmp,new}) so the provisioning module
can parse verification / credential-setup links. Standard library only.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import uuid
from pathlib import Path


class Sink:
    def __init__(self, maildir: Path) -> None:
        self.maildir = maildir
        for sub in ("tmp", "new"):
            (maildir / sub).mkdir(parents=True, exist_ok=True)

    def store(self, data: bytes) -> None:
        self.maildir.mkdir(parents=True, exist_ok=True)
        for sub in ("tmp", "new"):
            (self.maildir / sub).mkdir(parents=True, exist_ok=True)
        name = f"{int(asyncio.get_event_loop().time() * 1_000_000)}.{uuid.uuid4().hex}.b1"
        tmp = self.maildir / "tmp" / name
        tmp.write_bytes(data)
        os.link(tmp, self.maildir / "new" / name)
        tmp.unlink()


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, sink: Sink) -> None:
    peer = writer.get_extra_info("peername")
    print(f"[smtp-sink] connection from {peer}", flush=True)

    def send(line: str) -> None:
        writer.write((line + "\r\n").encode("utf-8"))

    send("220 sku-m1-browser-smtp-sink ready")
    data_mode = False
    auth_state = None
    data_buf = bytearray()
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=120)
        except (asyncio.TimeoutError, ConnectionError):
            break
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        if data_mode:
            if text == ".":
                send("250 OK message accepted")
                data_mode = False
                sink.store(bytes(data_buf))
                data_buf.clear()
            else:
                if text.startswith(".."):
                    text = text[1:]
                data_buf.extend((text + "\n").encode("utf-8"))
            continue
        verb = text.split(" ", 1)[0].upper()
        if auth_state == "await_username":
            auth_state = "await_password"
            send("334 UGFzc3dvcmQ6")
            continue
        if auth_state == "await_password":
            auth_state = None
            send("235 2.7.0 Authentication successful")
            continue
        if verb in ("EHLO", "HELO"):
            send("250-sku-m1-browser-smtp-sink")
            send("250 AUTH LOGIN")
        elif verb == "AUTH" and "LOGIN" in text.upper():
            auth_state = "await_username"
            send("334 VXNlcm5hbWU6")
        elif verb in ("MAIL", "RCPT"):
            send("250 OK")
        elif verb == "DATA":
            send("354 End data with <CR><LF>.<CR><LF>")
            data_mode = True
        elif verb == "RSET":
            send("250 OK")
        elif verb == "NOOP":
            send("250 OK")
        elif verb == "QUIT":
            send("221 Bye")
            break
        else:
            send("250 OK")
    try:
        await writer.drain()
    except ConnectionError:
        pass
    writer.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8103)
    parser.add_argument("--maildir", default="results/maildir")
    args = parser.parse_args()
    sink = Sink(Path(args.maildir))

    async def handler(reader, writer):
        try:
            await handle(reader, writer, sink)
        except Exception as exc:
            print(f"[smtp-sink] session error: {exc}", flush=True)
            try:
                writer.close()
            except Exception:
                pass

    server = await asyncio.start_server(handler, "127.0.0.1", args.port)
    print(f"[smtp-sink] listening on 127.0.0.1:{args.port}, maildir={args.maildir}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
