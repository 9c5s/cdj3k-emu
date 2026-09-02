# key-recovery — CDJ-3000 / CDJ-3000X ファーム LUKS 鍵の回収と検証ツール

`.UPD`（両機種のファーム）は標準 LUKS1（AES-256-XTS、PBKDF2-SHA256）で、slot0 を開けるのは
約 32 バイトの生バイナリ鍵ファイル `aes256.key`。ランダム鍵のため `.UPD` 単体からの総当たりは不可能。
実機（root 化済み）から鍵ファイルを吸い出して検証するのが本命の経路。

## 構成

- `collect_cdj3k_key.sh`：実機（root SSH）上で実行する鍵素材コレクタ。
  `dmsetup table --showkeys`（マスターキーを 16 進で取得）、`--key-file` 参照の全文検索、
  鍵ファイル候補（名前とサイズベース）の収集を行い `/tmp/cdj3k-key-loot.tar.gz` にまとめる。
- `keyhunt-src/`：検証オラクル。リポジトリ本体の `cdj3k-emu-firmware::decrypt_upd`（本物の LUKS 復号）で
  候補鍵を検証する。暗号を再実装しないので偽陰性が出ない。`Cargo.toml` は firmware クレートを
  相対パス（`../../../crates/cdj3k-emu-firmware`）で参照する独立ワークスペース。
- `luks_header_diff.py`：複数の `.UPD` の LUKS1 ヘッダを抽出して並べる比較ツール。
  cipher、mode、hash、iter、UUID、mk_digest が版間で同一かを一目で確認できる。
  CDJ-3000X の master key 版間同一性を確認したのはこれ（PEP 723 スクリプト、`uv run` で実行）。

## ワークフロー

1. 実機を root 化（emmaworley/cdj3k-root の方式: FAT32 USB に更新ファイル + authorized_keys →
   通常のファーム更新で SSH root 開通。ビルド済みリリースを使えば鍵無しでも root 化可能）。
2. 実機へ `collect_cdj3k_key.sh` を送って実行し、`/tmp/cdj3k-key-loot.tar.gz` を回収。
   ```sh
   host$ scp collect_cdj3k_key.sh <device>:/tmp/
   device# sh /tmp/collect_cdj3k_key.sh
   host$ scp <device>:/tmp/cdj3k-key-loot.tar.gz .
   host$ tar xzf cdj3k-key-loot.tar.gz
   ```
3. 候補を検証してファーム復号:
   ```sh
   host$ cd keyhunt-src && cargo build --release
   host$ ./target/release/keyhunt <CDJ3Kv322.UPD> --dir ../cdj3k-key-loot/candidates decrypted.iso
   ```
   一致すれば `aes256.key`（hex）を表示し、復号済み ISO を書き出す。
   その `aes256.key` を保存すればエミュの Install Firmware ウィザードにそのまま使える。

## 補足

- `refs-lines.txt` に更新スクリプトの `cryptsetup ... --key-file <path>` が出れば、鍵の正確な
  ファイルパスが分かる。そのファイルを直接 keyhunt に渡すのが確実。
- `dmsetup-showkeys.txt` に出るのは 64 バイトのマスターキー（keyfile ではない）。ウィザードには
  直接入らないが、`cryptsetup open --master-key-file` 相当で `.UPD` を直接復号する用途に使える。
- keyhunt は候補ファイルを raw と hex デコードの両形態で試す（crate 側で base64 も試行）。
- CDJ-3000X は 3 バージョン全てで master key が同一（`luks_header_diff.py` の出力が UUID、mk_digest、mk_salt、mk_iter の完全一致を示す）。
  1 個の `aes256.key` があれば v1.10、v1.20、v1.40 のすべてを復号できる。
- CDJ-3000 は版ごとに LUKS ヘッダが新規生成されているため、鍵同一性はヘッダ比較では判定不能。
  実機から鍵を得たのち、`keyhunt --dir` で `.tmp/firmware/CDJ-3000/*.UPD` に対して一括検証すれば確認できる。
