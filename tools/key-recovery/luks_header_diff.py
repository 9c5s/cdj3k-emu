#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""複数の .UPD の LUKS1 ヘッダを抽出して並べる。

同じ機種の複数バージョンの UPD を渡すと、各版の暗号パラメータと keyslot 情報を
表形式で出力する。cipher / mode / hash / mk_iter / uuid が全版で一貫していれば、
Pioneer が同じビルド運用で暗号化していることの傍証となる（鍵が同じかは、
実際に復号を試みるまで確定できない）。

usage:
  ./luks_header_diff.py <upd1> <upd2> ...
"""

import struct
import sys
from pathlib import Path

SLOT_ACTIVE = 0x00AC_71F3


def cstr(b: bytes) -> str:
    return b.split(b"\x00", 1)[0].decode("ascii", errors="replace")


def parse(path: Path) -> dict:
    with path.open("rb") as f:
        h = f.read(1024)
    if h[:6] != b"LUKS\xba\xbe":
        raise ValueError(f"{path}: not a LUKS1 container")
    ver = struct.unpack(">H", h[6:8])[0]
    cipher = cstr(h[8:40])
    mode = cstr(h[40:72])
    hash_spec = cstr(h[72:104])
    payload_offset = struct.unpack(">I", h[104:108])[0]
    key_bytes = struct.unpack(">I", h[108:112])[0]
    mk_iter = struct.unpack(">I", h[164:168])[0]
    uuid = cstr(h[168:208])
    slots = []
    for i in range(8):
        base = 208 + 48 * i
        state, iters = struct.unpack(">II", h[base : base + 8])
        km_start, stripes = struct.unpack(">II", h[base + 40 : base + 48])
        slots.append(
            {
                "idx": i,
                "active": state == SLOT_ACTIVE,
                "iterations": iters,
                "km_start": km_start,
                "stripes": stripes,
            }
        )
    return {
        "path": path,
        "size": path.stat().st_size,
        "luks_ver": ver,
        "cipher": cipher,
        "mode": mode,
        "hash_spec": hash_spec,
        "payload_offset": payload_offset,
        "key_bytes": key_bytes,
        "mk_iter": mk_iter,
        "uuid": uuid,
        "slots": slots,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    headers = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        try:
            headers.append(parse(p))
        except (OSError, ValueError) as e:
            print(f"skip {arg}: {e}", file=sys.stderr)
    if not headers:
        return 1

    cols = ["luks_ver", "cipher", "mode", "hash_spec", "key_bytes", "mk_iter", "uuid"]
    name_w = max(len(p.name) for p in (h["path"] for h in headers))
    fmt = f"  {{:<{name_w}}}  " + "  ".join(["{:<10}"] * (len(cols) - 1)) + "  {}"
    print(fmt.format("file", *cols[:-1], cols[-1]))
    for h in headers:
        print(
            fmt.format(
                h["path"].name,
                h["luks_ver"],
                h["cipher"],
                h["mode"],
                h["hash_spec"],
                h["key_bytes"],
                h["mk_iter"],
                h["uuid"],
            )
        )

    print("\n有効 keyslot 一覧（active スロットのみ）")
    for h in headers:
        actives = [s for s in h["slots"] if s["active"]]
        parts = [
            f"slot{s['idx']}(iter={s['iterations']}, stripes={s['stripes']})"
            for s in actives
        ]
        print(f"  {h['path'].name:<{name_w}}  {', '.join(parts)}")

    print("\nバージョン間で一貫している / 変化しているフィールド")
    for field in ["cipher", "mode", "hash_spec", "key_bytes", "mk_iter"]:
        values = {h[field] for h in headers}
        mark = "一貫" if len(values) == 1 else "変化あり"
        print(f"  {field:<15} {mark}  values={sorted(values)}")

    uuids = {h["uuid"] for h in headers}
    if len(uuids) == 1:
        print(f"  {'uuid':<15} 全版で同一（異常。通常はコンテナごとに一意）  {uuids.pop()}")
    else:
        print(f"  {'uuid':<15} 版ごとに異なる（正常）  count={len(uuids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
