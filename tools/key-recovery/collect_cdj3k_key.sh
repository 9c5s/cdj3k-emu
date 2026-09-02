#!/bin/sh
# SPDX-License-Identifier: MIT OR Apache-2.0
# CDJ-3000（root 化済み）上で LUKS 復号鍵の素材を収集する。
# 収集物を /tmp/cdj3k-key-loot.tar.gz にまとめる。ホストへ scp で回収し、
# keyhunt --dir で本物の復号コードにより総当たり検証する。
#
# 使い方（デバイス側、SSH root で）:
#   sh collect_cdj3k_key.sh
#   （回収）host$ scp cdj3000:/tmp/cdj3k-key-loot.tar.gz .
#
# 注意: 実機の rootfs は非暗号（eMMC）。鍵ファイル aes256.key はこの中にある想定。
set -u
umask 077 # 収集物は復号鍵・マスターキーを含む機密。新規ファイル 0600 / ディレクトリ 0700 に制限する
OUT=/tmp/cdj3k-key-loot
rm -rf "$OUT" 2>/dev/null
mkdir -p "$OUT/candidates"
log() { echo "[*] $*"; }

# 1) dm-crypt が開いていればマスターキー(64B hex)を露出させる
if command -v dmsetup >/dev/null 2>&1; then
  log "dmsetup table --showkeys"
  dmsetup table --showkeys >"$OUT/dmsetup-showkeys.txt" 2>&1 || true
fi
# LUKS ヘッダ情報（有効スロット等）も控える
if command -v cryptsetup >/dev/null 2>&1; then
  cryptsetup --version >"$OUT/cryptsetup-version.txt" 2>&1 || true
fi

# 2) cryptsetup / key-file / luksOpen / aes256 の参照箇所を全文検索。
#    更新スクリプトが --key-file <path> の形で鍵パスを教えてくれることが多い。
log "grep cryptsetup / key-file references (更新スクリプトが鍵パスを示す)"
: >"$OUT/refs.txt"
for d in /etc /usr /sbin /bin /opt /root /home /data /mnt /lib /var; do
  [ -d "$d" ] && grep -rIl -e cryptsetup -e key-file -e luksOpen -e aes256 "$d" 2>/dev/null
done | sort -u >>"$OUT/refs.txt"
: >"$OUT/refs-lines.txt"
while IFS= read -r f; do
  [ -f "$f" ] || continue
  echo "### $f" >>"$OUT/refs-lines.txt"
  grep -nE "cryptsetup|key-file|luksOpen|aes256|\.key" "$f" 2>/dev/null >>"$OUT/refs-lines.txt"
done <"$OUT/refs.txt"

# 3) 鍵ファイル候補を収集（名前ベース + サイズベース 16..64B の小バイナリ）
log "find key-like files (名前 / サイズ)"
find / -xdev \( -iname "aes256.key" -o -iname "*.key" -o -iname "*luks*" -o -iname "*aes*key*" \) -type f 2>/dev/null >"$OUT/named.txt"
find / -xdev -type f -size +15c -size -65c 2>/dev/null >"$OUT/smallfiles.txt"

i=0
{ cat "$OUT/named.txt"; cat "$OUT/smallfiles.txt"; } | sort -u | while IFS= read -r f; do
  [ -f "$f" ] || continue
  i=$((i + 1))
  [ "$i" -gt 4000 ] && break
  safe=$(echo "$f" | sed 's,/,__,g')
  cp "$f" "$OUT/candidates/$safe" 2>/dev/null || true
done
log "candidates collected: $(ls "$OUT/candidates" 2>/dev/null | wc -l)"

# 4) パッケージ化
tar czf "${OUT}.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null
chmod 600 "${OUT}.tar.gz" 2>/dev/null || true # 鍵素材を含むアーカイブは所有者のみ読取可に
log "done -> ${OUT}.tar.gz"
ls -l "${OUT}.tar.gz" 2>/dev/null
echo
echo "回収して検証:"
echo "  host\$ scp <device>:${OUT}.tar.gz ."
echo "  host\$ tar xzf cdj3k-key-loot.tar.gz"
echo "  host\$ keyhunt <CDJ3Kv322.UPD> --dir cdj3k-key-loot/candidates decrypted.iso"
