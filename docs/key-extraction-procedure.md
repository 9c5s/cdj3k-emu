# CDJ-3000 復号鍵の抽出手順書

## 概要

CDJ-3000 のファームウェア更新ファイル（`.UPD`）を復号するための鍵を、実機から抽出する手順を示す。
`.UPD` は LUKS1 で暗号化されており、復号には約 32 バイトのバイナリ鍵ファイル（`aes256.key`）が必要である。
この鍵は実機の非暗号領域に格納されているため、root 化した実機から直接読み出す。

技術的背景と解析の詳細は [firmware-key-recovery.md](firmware-key-recovery.md) を参照。

## 前提条件

### 機材

- CDJ-3000 実機（電源投入可能な状態）
- USB メモリ（FAT32 フォーマット済み、1 GB 以上）
- ホスト PC（SSH クライアントと Rust ツールチェインが利用可能）
- CDJ-3000 とホスト PC を接続する LAN ケーブル、またはルーターを介したネットワーク

### ソフトウェア

- SSH クライアント（`ssh`、`scp`）
- Rust ツールチェイン（`cargo`）: keyhunt のビルドに使用
- `.UPD` ファイル（例: `CDJ3Kv322.UPD`）: 鍵の検証対象

### 外部リソース

- [emmaworley/cdj3k-root](https://github.com/emmaworley/cdj3k-root): CDJ-3000 を root 化するツール。Releases にビルド済みの更新ファイルがある

## 手順

### 1. CDJ-3000 のファームウェアバージョンを確認する

CDJ-3000 の UTILITY 画面でファームウェアバージョンを確認する。
cdj3k-root のリリースが対応するバージョンと一致している必要がある。

> cdj3k-root のビルド済みリリースは特定のファームバージョン向けに提供されている。
> 機体のバージョンと一致しない場合は、自分でビルドするか、対応バージョンにダウングレードする必要がある。

### 2. root 化用 USB メディアを準備する

1. cdj3k-root の [Releases](https://github.com/emmaworley/cdj3k-root/releases) から、機体のファームバージョンに対応するアーカイブを取得する
2. USB メモリを FAT32 でフォーマットする
3. アーカイブの内容を USB メモリのルートに展開する
4. SSH 公開鍵を所定の場所に配置する（cdj3k-root の README に従う）

```
USB メモリの構成例:
/
├── PIONEER/
│   └── （cdj3k-root が指定する更新ファイル群）
└── authorized_keys   （SSH 公開鍵）
```

> SSH 鍵ペアが手元にない場合は `ssh-keygen -t ed25519` で生成する。
> 公開鍵（`~/.ssh/id_ed25519.pub`）を USB メモリに配置する。

### 3. CDJ-3000 を root 化する

1. CDJ-3000 の電源を切る
2. 準備した USB メモリを CDJ-3000 の USB 端子に挿入する
3. CDJ-3000 の電源を入れる
4. 通常のファームウェア更新と同じ操作で更新を開始する
5. 更新が完了したら CDJ-3000 を再起動する

更新後、SSH による root 接続が有効になる。

### 4. CDJ-3000 の IP アドレスを特定する

CDJ-3000 を LAN ケーブルでネットワークに接続する。
IP アドレスの特定方法はネットワーク構成に依存するが、代表的な方法を示す。

```sh
# ルーター経由の場合: ルーターの DHCP リース一覧を確認する

# 直結の場合: link-local アドレスを使用するか、arp テーブルを確認する
arp -a
```

### 5. SSH で CDJ-3000 に接続する

```sh
ssh root@<CDJ-3000のIPアドレス>
```

接続できれば root 化は成功している。接続できない場合は手順 3 を確認する。

### 6. 鍵収集スクリプトを転送して実行する

ホスト PC 側で、このリポジトリの収集スクリプトを CDJ-3000 に送り、実行する。

```sh
# ホスト PC で実行
scp tools/key-recovery/collect_cdj3k_key.sh root@<CDJ-3000のIPアドレス>:/tmp/
```

```sh
# CDJ-3000 上で実行（SSH セッション内）
sh /tmp/collect_cdj3k_key.sh
```

スクリプトは以下を収集し、`/tmp/cdj3k-key-loot.tar.gz` にまとめる。

- `dmsetup-showkeys.txt`: dm-crypt が開いている場合のマスターキー
- `refs.txt` / `refs-lines.txt`: `cryptsetup --key-file` の参照箇所（鍵のファイルパスが判明する）
- `candidates/`: 名前とサイズに基づく鍵ファイル候補

### 7. 収集結果をホスト PC に回収する

```sh
# ホスト PC で実行
scp root@<CDJ-3000のIPアドレス>:/tmp/cdj3k-key-loot.tar.gz .
tar xzf cdj3k-key-loot.tar.gz
```

### 8. 収集結果を確認する

回収したアーカイブの内容を確認し、有力な候補がないか調べる。

```sh
# refs-lines.txt に --key-file のパスが記録されていれば最有力
cat cdj3k-key-loot/refs-lines.txt | grep -i "key-file"

# 鍵ファイル候補の一覧
ls -la cdj3k-key-loot/candidates/
```

`refs-lines.txt` に `cryptsetup ... --key-file /path/to/keyfile` のような記述があれば、そのパスが鍵ファイルの正確な場所である。
候補に含まれていなければ、SSH で CDJ-3000 に戻り、該当ファイルを直接取得する。

```sh
# 鍵のパスが判明した場合、直接取得する
scp root@<CDJ-3000のIPアドレス>:<判明したパス> cdj3k-key-loot/candidates/
```

### 9. keyhunt で鍵候補を検証する

keyhunt は、リポジトリ本体の復号コード（`cdj3k-emu-firmware::decrypt_upd`）を使って候補鍵を検証するツールである。
暗号処理を再実装していないため、偽陰性（本物の鍵を見逃すこと）が起きない。

```sh
# keyhunt をビルドする
cd tools/key-recovery/keyhunt-src
cargo build --release

# 候補ディレクトリを一括検証する
./target/release/keyhunt <UPDファイルのパス> --dir ../../../cdj3k-key-loot/candidates decrypted.iso
```

- 一致する鍵が見つかった場合: `*** FOUND ***` と表示され、鍵の hex 値と復号済み ISO が出力される
- 一致しなかった場合: `no candidate matched` と表示される

### 10. 鍵を保存してエミュレータに適用する

鍵が見つかった場合、keyhunt が出力した hex 値をバイナリファイルとして保存する。

```sh
# keyhunt の出力例:
#   *** FOUND *** cdj3k-key-loot/candidates/__path__to__aes256.key
#   keyfile hex (32 bytes): 0123456789abcdef...
#   decrypted payload written to: decrypted.iso

# hex 値をバイナリの鍵ファイルに変換する
echo -n "0123456789abcdef..." | xxd -r -p > aes256.key
```

保存した `aes256.key` を、エミュレータの Install Firmware ウィザードの鍵ファイル入力欄に指定する。

## トラブルシューティング

### SSH に接続できない

- CDJ-3000 が LAN に接続されており、IP アドレスが正しいことを確認する
- root 化の更新が正常に完了したことを確認する（更新中にエラーが出ていないか）
- `ssh -v root@<IP>` で詳細ログを確認する
- cdj3k-root のリリースが機体のファームバージョンに対応しているか確認する

### 鍵候補が見つからない（candidates が空に近い）

- `refs-lines.txt` を確認し、鍵ファイルの正確なパスを特定する
- SSH で CDJ-3000 に接続し、`find / -iname "*.key" -type f` で手動検索する
- ファームウェア更新中（LUKS が開いた状態）に `dmsetup table --showkeys` を実行する

### keyhunt で一致しない

- `refs-lines.txt` の `--key-file` パスから鍵を直接取得したか確認する
- マスターキー（`dmsetup-showkeys.txt`）が取得できている場合、`cryptsetup open --master-key-file` で直接復号を試みる

```sh
# マスターキーの hex を取得（dmsetup-showkeys.txt から）
MASTER_KEY_HEX="..."

# hex をバイナリに変換
echo -n "$MASTER_KEY_HEX" | xxd -r -p > master.key

# マスターキーで直接復号（LUKS スロットを経由しない）
cryptsetup open --type luks --master-key-file master.key <UPDファイル> firmware_dec
```

### keyhunt のビルドに失敗する

- `cdj3k-emu-firmware` クレートへのパスが正しいことを確認する（`Cargo.toml` の相対パス `../../../crates/cdj3k-emu-firmware`）
- リポジトリのルートで `cargo check -p cdj3k-emu-firmware` が通ることを確認する

## 鍵ファイルとマスターキーの違い

抽出時に二種類の鍵を混同しないよう注意する。

| 項目 | 鍵ファイル（`aes256.key`） | マスターキー |
|---|---|---|
| サイズ | 約 32 バイト | 64 バイト |
| 取得方法 | rootfs から直接読み出し | `dmsetup table --showkeys` |
| エミュレータのウィザード | そのまま使用可能 | 直接入力不可 |
| `.UPD` の復号 | `cryptsetup luksOpen --key-file` | `cryptsetup open --master-key-file` |

エミュレータに使うには鍵ファイルが必要である。
マスターキーしか得られない場合は、`.UPD` の復号は可能だが、エミュレータのウィザードには別途対応が必要となる。

## root 化の解除

鍵の抽出が完了したら、CDJ-3000 を元の状態に戻すことができる。
root 化はオーバーレイパーティション上の `pdj.tar.gz` の差し替えだけで実現されており、rootfs 本体やブートローダーは変更されていない。

SSH で CDJ-3000 に接続し、以下を実行する。

```sh
~/.unroot.sh
```

スクリプトはオーバーレイ tar を削除して再起動する。
再起動後は SSH アクセスと authorized_keys が消え、元の状態に戻る。

Rockchip モデルは自動で再起動する。
Renesas モデルは手動で電源を入れ直す必要がある。

Pioneer 公式ファームウェアを適用しても同様に復旧できるが、unroot スクリプトで十分である。

## セキュリティ上の注意

- 抽出した鍵ファイルは機密として扱い、公開リポジトリに含めない
- 収集スクリプトは `umask 077` でアーカイブを作成する（所有者のみ読取可）
- 作業完了後、CDJ-3000 上の `/tmp/cdj3k-key-loot*` を削除する
