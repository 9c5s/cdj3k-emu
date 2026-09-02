// keyhunt: 本物の LUKS 復号コード(cdj3k-emu-firmware::decrypt_upd)を使い、
// 鍵候補が .UPD の slot0 を開けるかを検証するオラクル。
//   モード1: --blob <candidates.bin>  length-prefixed バイナリ候補
//   モード2: --dir  <dir>             ディレクトリ内の各ファイルを生鍵候補として総当たり
// いずれも各候補について raw / hex-decode / base64 は crate 側でも試行される。
use std::io::Read;
use std::path::{Path, PathBuf};
use std::time::Instant;
use cdj3k_emu_firmware::{decrypt_upd, LuksKey};

fn main() {
    let a: Vec<String> = std::env::args().collect();
    if a.len() < 5 {
        eprintln!("usage: keyhunt <upd> --blob <candidates.bin> <out>");
        eprintln!("       keyhunt <upd> --dir  <candidate_dir>   <out>");
        std::process::exit(2);
    }
    let upd = &a[1];
    let mode = &a[2];
    let src = &a[3];
    let out = &a[4];

    let mut cands: Vec<(String, Vec<u8>)> = Vec::new();
    match mode.as_str() {
        "--blob" => {
            let mut buf = Vec::new();
            std::fs::File::open(src).expect("open blob").read_to_end(&mut buf).unwrap();
            let mut p = 0usize;
            let rd = |b: &[u8], p: &mut usize| { let v = u32::from_le_bytes(b[*p..*p+4].try_into().unwrap()); *p+=4; v };
            let n = rd(&buf, &mut p) as usize;
            for _ in 0..n { let l = rd(&buf, &mut p) as usize; cands.push((format!("blob[{l}B]"), buf[p..p+l].to_vec())); p+=l; }
        }
        "--dir" => {
            let mut files: Vec<PathBuf> = Vec::new();
            collect(Path::new(src), &mut files);
            files.sort();
            for f in files {
                if let Ok(b) = std::fs::read(&f) {
                    // 生バイト
                    cands.push((f.display().to_string(), b.clone()));
                    // hex デコード形（テキストなら）
                    if let Ok(t) = std::str::from_utf8(&b) {
                        let hx: String = t.chars().filter(|c| !c.is_ascii_whitespace() && *c!=':').collect();
                        if !hx.is_empty() && hx.len()%2==0 && hx.chars().all(|c| c.is_ascii_hexdigit()) {
                            if let Ok(d) = hex_decode(&hx) { cands.push((format!("{} [hex-decoded]", f.display()), d)); }
                        }
                    }
                }
            }
        }
        _ => { eprintln!("unknown mode {mode}"); std::process::exit(2); }
    }

    println!("candidates: {}", cands.len());
    let start = Instant::now();
    for (i,(label, bytes)) in cands.iter().enumerate() {
        let key = LuksKey::from_bytes(bytes.clone());
        if decrypt_upd(Path::new(upd), &key, Path::new(out)).is_ok() {
            println!("\n*** FOUND *** {label}");
            println!("keyfile hex ({} bytes): {}", bytes.len(), hex_str(bytes));
            println!("decrypted payload written to: {out}");
            return;
        }
        if i % 20 == 0 { println!("[{:6.1}s] #{i:>5} {}", start.elapsed().as_secs_f64(), label); }
    }
    println!("\nno candidate matched ({} tried, {:.1}s)", cands.len(), start.elapsed().as_secs_f64());
}

fn collect(dir: &Path, out: &mut Vec<PathBuf>) {
    if let Ok(rd) = std::fs::read_dir(dir) {
        for e in rd.flatten() {
            let p = e.path();
            if p.is_dir() { collect(&p, out); }
            else if p.is_file() {
                if let Ok(m) = e.metadata() { if m.len() >= 1 && m.len() <= 8192 { out.push(p); } }
            }
        }
    }
}
fn hex_decode(s: &str) -> Result<Vec<u8>,()> {
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i+2],16).map_err(|_|())).collect()
}
fn hex_str(b: &[u8]) -> String { b.iter().map(|x| format!("{x:02x}")).collect() }
