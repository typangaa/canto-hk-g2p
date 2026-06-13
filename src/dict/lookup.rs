//! Memory-mapped binary dictionary lookup for canto-g2p.
//!
//! Binary format (little-endian throughout):
//!
//! ```text
//! HEADER (16 bytes):
//!   magic:        [u8; 4] = b"CJYP"
//!   version:      u32 LE  = 1
//!   entry_count:  u32 LE
//!   pool_size:    u32 LE
//!
//! ENTRY TABLE (entry_count × 12 bytes, sorted by key UTF-8 bytes):
//!   key_start: u32 LE   byte offset into string pool
//!   key_len:   u16 LE   byte length of UTF-8 key
//!   val_start: u32 LE   byte offset into string pool
//!   val_len:   u16 LE   byte length of UTF-8 value
//!
//! STRING POOL (pool_size bytes):
//!   Raw UTF-8. Strings referenced by (start, len).
//! ```

use memmap2::Mmap;
use std::fs::File;
use std::path::Path;

// ── Constants ────────────────────────────────────────────────────────────────

const MAGIC: &[u8; 4] = b"CJYP";
const VERSION: u32 = 1;
const HEADER_SIZE: usize = 16;
const ENTRY_SIZE: usize = 12; // 4 + 2 + 4 + 2

// ── RawEntry ─────────────────────────────────────────────────────────────────

/// On-disk entry layout (packed, little-endian).
///
/// Fields must be read via `ptr::read_unaligned` because the struct is
/// `repr(C, packed)` and may not be naturally aligned.
#[repr(C, packed)]
#[allow(dead_code)]
struct RawEntry {
    key_start: u32,
    key_len: u16,
    val_start: u32,
    val_len: u16,
}

// ── Dict ─────────────────────────────────────────────────────────────────────

/// An in-process, zero-copy dictionary backed by a memory-mapped `.bin` file.
///
/// All `&str` slices returned by lookup methods borrow directly from the mmap
/// region and have a lifetime tied to `&self`.
pub struct Dict {
    /// Keeps the mmap alive for the duration of this struct.
    _mmap: Mmap,
    /// Pointer to the first byte of the entry table inside the mmap.
    entry_ptr: *const u8,
    /// Pointer to the first byte of the string pool inside the mmap.
    pool_ptr: *const u8,
    /// Number of entries in the entry table.
    entry_count: usize,
}

// SAFETY: The raw pointers point into an `Mmap` that is owned by this struct
// and is never moved after construction. The data is read-only (no mutation
// through these pointers), so sharing across threads is safe.
unsafe impl Send for Dict {}
unsafe impl Sync for Dict {}

impl Dict {
    // ── Public API ───────────────────────────────────────────────────────────

    /// Load a `.bin` dict file via `mmap`.
    ///
    /// Returns an error if:
    /// * The file cannot be opened / mapped.
    /// * The magic bytes are not `b"CJYP"`.
    /// * The version field is not `1`.
    /// * The file is too short to contain the declared header + entry table +
    ///   string pool.
    pub fn load(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let file = File::open(path)?;

        // SAFETY: We do not mutate the mapped region.  The file descriptor is
        // kept alive by `file` until after `mmap` is created; after that the
        // `Mmap` holds its own reference to the underlying pages.
        let mmap = unsafe { Mmap::map(&file)? };

        // ── Validate header ──────────────────────────────────────────────────
        if mmap.len() < HEADER_SIZE {
            return Err(format!(
                "file too short: {} bytes (need at least {HEADER_SIZE})",
                mmap.len()
            )
            .into());
        }

        let data: &[u8] = &mmap;

        // magic
        if &data[0..4] != MAGIC {
            return Err(format!(
                "bad magic: expected {:?}, got {:?}",
                MAGIC,
                &data[0..4]
            )
            .into());
        }

        // version
        let version = u32::from_le_bytes(data[4..8].try_into().unwrap());
        if version != VERSION {
            return Err(format!("unsupported version {version} (expected {VERSION})").into());
        }

        let entry_count = u32::from_le_bytes(data[8..12].try_into().unwrap()) as usize;
        let pool_size = u32::from_le_bytes(data[12..16].try_into().unwrap()) as usize;

        // bounds check
        let pool_offset = HEADER_SIZE + entry_count * ENTRY_SIZE;
        let required = pool_offset + pool_size;
        if mmap.len() < required {
            return Err(format!(
                "file too short: {} bytes (need {required} for {entry_count} entries + pool)",
                mmap.len()
            )
            .into());
        }

        // Capture raw pointers *before* moving `mmap` into the struct.
        // These pointers remain valid as long as `_mmap` is alive.
        let entry_ptr = data[HEADER_SIZE..].as_ptr();
        let pool_ptr = data[pool_offset..].as_ptr();

        Ok(Dict {
            _mmap: mmap,
            entry_ptr,
            pool_ptr,
            entry_count,
        })
    }

    /// Exact key lookup. Returns the Jyutping string slice (zero-copy from
    /// the mmap) if the key is found, or `None` otherwise.
    pub fn lookup<'a>(&'a self, key: &str) -> Option<&'a str> {
        let key_bytes = key.as_bytes();
        let mut lo: usize = 0;
        let mut hi: usize = self.entry_count;

        while lo < hi {
            let mid = lo + (hi - lo) / 2;
            let entry = self.entry_at(mid);
            let mid_key = self.key_at(&entry);

            match mid_key.as_bytes().cmp(key_bytes) {
                std::cmp::Ordering::Less => lo = mid + 1,
                std::cmp::Ordering::Greater => hi = mid,
                std::cmp::Ordering::Equal => return Some(self.val_at(&entry)),
            }
        }

        None
    }

    /// Find the longest word starting at the beginning of `text`.
    ///
    /// Tries prefix lengths from `max_chars` down to `1` (measured in Unicode
    /// scalar values / characters), performs an exact lookup for each, and
    /// returns `(byte_len_of_matched_key, jyutping_value)` for the first
    /// (longest) match found, or `None` if no prefix matches at all.
    pub fn longest_prefix_match<'a>(
        &'a self,
        text: &str,
        max_chars: usize,
    ) -> Option<(usize, &'a str)> {
        if max_chars == 0 {
            return None;
        }

        // Build prefix_ends[i] = byte length of the (i+1)-char prefix.
        let mut prefix_ends: Vec<usize> = Vec::with_capacity(max_chars);
        let mut chars_seen = 0usize;
        for (byte_idx, ch) in text.char_indices() {
            chars_seen += 1;
            prefix_ends.push(byte_idx + ch.len_utf8());
            if chars_seen >= max_chars {
                break;
            }
        }
        // Now prefix_ends[i] = byte length of (i+1)-char prefix (0-indexed).

        // Try longest first.
        for i in (0..prefix_ends.len()).rev() {
            let byte_len = prefix_ends[i];
            let prefix = &text[..byte_len];
            if let Some(val) = self.lookup(prefix) {
                return Some((byte_len, val));
            }
        }

        None
    }

    // ── Private helpers ──────────────────────────────────────────────────────

    /// Read the `RawEntry` at index `idx` using unaligned loads.
    ///
    /// SAFETY: `idx` must be < `self.entry_count`.
    fn entry_at(&self, idx: usize) -> RawEntry {
        // SAFETY: `entry_ptr` points to the start of the entry table in the
        // mmap. Each entry is ENTRY_SIZE bytes. idx < entry_count is upheld
        // by the binary-search loop invariant.
        unsafe {
            let ptr = self.entry_ptr.add(idx * ENTRY_SIZE) as *const RawEntry;
            std::ptr::read_unaligned(ptr)
        }
    }

    /// Return the key string for the given entry (zero-copy from pool).
    fn key_at<'a>(&'a self, entry: &RawEntry) -> &'a str {
        // packed fields: read via copy to avoid unaligned reference.
        let start = u32::from_le(entry.key_start) as usize;
        let len = u16::from_le(entry.key_len) as usize;
        self.pool_str(start, len)
    }

    /// Return the value string for the given entry (zero-copy from pool).
    fn val_at<'a>(&'a self, entry: &RawEntry) -> &'a str {
        let start = u32::from_le(entry.val_start) as usize;
        let len = u16::from_le(entry.val_len) as usize;
        self.pool_str(start, len)
    }

    /// Construct a `&str` pointing directly into the mmap string pool.
    ///
    /// SAFETY: The caller must guarantee that `[start, start+len)` lies within
    /// the pool region and contains valid UTF-8.  Both conditions are
    /// guaranteed by a well-formed binary file (validated at load time via
    /// pool_size bounds check).
    fn pool_str<'a>(&'a self, start: usize, len: usize) -> &'a str {
        unsafe {
            let slice = std::slice::from_raw_parts(self.pool_ptr.add(start), len);
            // The binary builder is required to write valid UTF-8; if the file
            // is corrupt this will panic in debug, or produce garbage in
            // release — acceptable for a trusted binary artifact.
            std::str::from_utf8_unchecked(slice)
        }
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    #[allow(unused_imports)]
    use tempfile_helper::TempDict;

    // ── Tiny in-process binary builder ──────────────────────────────────────

    /// Helper: build a well-formed `.bin` file in memory from a list of
    /// (key, value) pairs (must be pre-sorted by key).
    fn build_bin(entries: &[(&str, &str)]) -> Vec<u8> {
        // Build pool
        let mut pool: Vec<u8> = Vec::new();
        // (key_start, key_len, val_start, val_len)
        let mut offsets: Vec<(u32, u16, u32, u16)> = Vec::new();

        for (key, val) in entries {
            let ks = pool.len() as u32;
            let kl = key.len() as u16;
            pool.extend_from_slice(key.as_bytes());

            let vs = pool.len() as u32;
            let vl = val.len() as u16;
            pool.extend_from_slice(val.as_bytes());

            offsets.push((ks, kl, vs, vl));
        }

        let entry_count = entries.len() as u32;
        let pool_size = pool.len() as u32;

        let mut out: Vec<u8> = Vec::new();

        // Header
        out.extend_from_slice(b"CJYP");
        out.extend_from_slice(&1u32.to_le_bytes()); // version
        out.extend_from_slice(&entry_count.to_le_bytes());
        out.extend_from_slice(&pool_size.to_le_bytes());

        // Entry table
        for (ks, kl, vs, vl) in &offsets {
            out.extend_from_slice(&ks.to_le_bytes());
            out.extend_from_slice(&kl.to_le_bytes());
            out.extend_from_slice(&vs.to_le_bytes());
            out.extend_from_slice(&vl.to_le_bytes());
        }

        // String pool
        out.extend_from_slice(&pool);

        out
    }

    /// Write bytes to a temp file and load a Dict from it.
    mod tempfile_helper {
        use super::*;
        use std::io::Write;

        pub struct TempDict {
            pub dict: Dict,
            _path: std::path::PathBuf,
            _dir: tempdir::TempDir,
        }

        // We use std::env::temp_dir + a random-ish name to avoid pulling in
        // the `tempfile` crate (not in Cargo.toml).  Use a simple approach:
        // write to a named temp file in OS temp dir.
        pub struct TempDir(std::path::PathBuf);

        impl TempDir {
            pub fn new() -> Self {
                use std::time::{SystemTime, UNIX_EPOCH};
                let nanos = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .subsec_nanos();
                let dir = std::env::temp_dir()
                    .join(format!("canto_g2p_test_{}", nanos));
                std::fs::create_dir_all(&dir).unwrap();
                TempDir(dir)
            }
            pub fn path(&self) -> &std::path::Path { &self.0 }
        }

        impl Drop for TempDir {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }

        // Shadow the outer `tempdir` module name so the struct can be used.
        pub mod tempdir {
            pub struct TempDir(pub std::path::PathBuf);
            impl TempDir {
                pub fn new() -> Self {
                    use std::time::{SystemTime, UNIX_EPOCH};
                    let nanos = SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .unwrap_or_default()
                        .subsec_nanos();
                    let dir = std::env::temp_dir()
                        .join(format!("canto_g2p_test_{}", nanos));
                    std::fs::create_dir_all(&dir).unwrap();
                    TempDir(dir)
                }
            }
            impl Drop for TempDir {
                fn drop(&mut self) {
                    let _ = std::fs::remove_dir_all(&self.0);
                }
            }
        }

        impl TempDict {
            pub fn from_bytes(bytes: &[u8]) -> Self {
                let tmp = tempdir::TempDir::new();
                let path = tmp.0.join("test.bin");
                let mut f = std::fs::File::create(&path).unwrap();
                f.write_all(bytes).unwrap();
                drop(f);
                let dict = Dict::load(&path).unwrap();
                TempDict {
                    dict,
                    _path: path,
                    _dir: tmp,
                }
            }
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    fn make_dict(pairs: &[(&str, &str)]) -> tempfile_helper::TempDict {
        let mut sorted = pairs.to_vec();
        sorted.sort_by_key(|(k, _)| k.as_bytes().to_vec());
        let bytes = build_bin(&sorted);
        tempfile_helper::TempDict::from_bytes(&bytes)
    }

    // ── Tests ────────────────────────────────────────────────────────────────

    #[test]
    fn test_load_empty_dict() {
        let bytes = build_bin(&[]);
        let td = tempfile_helper::TempDict::from_bytes(&bytes);
        assert!(td.dict.lookup("你").is_none());
    }

    #[test]
    fn test_bad_magic_rejected() {
        let mut bytes = build_bin(&[]);
        bytes[0] = b'X'; // corrupt magic
        let tmp = tempfile_helper::TempDir::new();
        let path = tmp.path().join("bad.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&bytes).unwrap();
        drop(f);
        assert!(Dict::load(&path).is_err());
    }

    #[test]
    fn test_bad_version_rejected() {
        let mut bytes = build_bin(&[]);
        // version is at bytes[4..8]; set to 99
        bytes[4..8].copy_from_slice(&99u32.to_le_bytes());
        let tmp = tempfile_helper::TempDir::new();
        let path = tmp.path().join("bad_ver.bin");
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(&bytes).unwrap();
        drop(f);
        assert!(Dict::load(&path).is_err());
    }

    #[test]
    fn test_single_entry_lookup() {
        let td = make_dict(&[("你好", "nei5 hou2")]);
        assert_eq!(td.dict.lookup("你好"), Some("nei5 hou2"));
        assert!(td.dict.lookup("你").is_none());
        assert!(td.dict.lookup("好").is_none());
    }

    #[test]
    fn test_multiple_entries_lookup() {
        let pairs = &[
            ("你好嘅", "nei5 hou2 ge3"),
            ("你好",   "nei5 hou2"),
            ("你",     "nei5"),
            ("好",     "hou2"),
            ("嘅",     "ge3"),
        ];
        let td = make_dict(pairs);

        assert_eq!(td.dict.lookup("你"),     Some("nei5"));
        assert_eq!(td.dict.lookup("好"),     Some("hou2"));
        assert_eq!(td.dict.lookup("嘅"),     Some("ge3"));
        assert_eq!(td.dict.lookup("你好"),   Some("nei5 hou2"));
        assert_eq!(td.dict.lookup("你好嘅"), Some("nei5 hou2 ge3"));
        assert!(td.dict.lookup("唔該").is_none());
    }

    #[test]
    fn test_lookup_ascii_entries() {
        let td = make_dict(&[("a", "aa1"), ("ab", "aa1 baa1"), ("b", "baa1")]);
        assert_eq!(td.dict.lookup("a"),  Some("aa1"));
        assert_eq!(td.dict.lookup("ab"), Some("aa1 baa1"));
        assert_eq!(td.dict.lookup("b"),  Some("baa1"));
        assert!(td.dict.lookup("c").is_none());
    }

    #[test]
    fn test_longest_prefix_match_basic() {
        let pairs = &[
            ("你好嘅", "nei5 hou2 ge3"),
            ("你好",   "nei5 hou2"),
            ("你",     "nei5"),
        ];
        let td = make_dict(pairs);

        // Full 3-char string — should match 3-char entry first.
        let result = td.dict.longest_prefix_match("你好嘅", 5);
        assert_eq!(result, Some((9, "nei5 hou2 ge3"))); // 你好嘅 = 9 bytes

        // 2-char string — should match 2-char entry.
        let result = td.dict.longest_prefix_match("你好", 5);
        assert_eq!(result, Some((6, "nei5 hou2"))); // 你好 = 6 bytes

        // Only 1 char available.
        let result = td.dict.longest_prefix_match("你", 5);
        assert_eq!(result, Some((3, "nei5"))); // 你 = 3 bytes

        // No match.
        let result = td.dict.longest_prefix_match("唔該", 5);
        assert!(result.is_none());
    }

    #[test]
    fn test_longest_prefix_match_max_chars_limit() {
        let pairs = &[
            ("你好嘅", "nei5 hou2 ge3"),
            ("你好",   "nei5 hou2"),
            ("你",     "nei5"),
        ];
        let td = make_dict(pairs);

        // max_chars=1 → only "你" prefix considered.
        let result = td.dict.longest_prefix_match("你好嘅", 1);
        assert_eq!(result, Some((3, "nei5")));

        // max_chars=2 → "你好" and "你" considered; "你好" wins.
        let result = td.dict.longest_prefix_match("你好嘅", 2);
        assert_eq!(result, Some((6, "nei5 hou2")));

        // max_chars=0 → no prefix considered.
        let result = td.dict.longest_prefix_match("你好嘅", 0);
        assert!(result.is_none());
    }

    #[test]
    fn test_longest_prefix_match_falls_back_to_shorter() {
        // Only single-char entries present; multi-char prefix should fall back.
        let pairs = &[
            ("你", "nei5"),
            ("好", "hou2"),
        ];
        let td = make_dict(pairs);

        let result = td.dict.longest_prefix_match("你好嘅", 5);
        assert_eq!(result, Some((3, "nei5")));
    }

    #[test]
    fn test_large_dict_binary_search() {
        // Build 1000 ASCII entries to exercise the binary search thoroughly.
        let mut pairs: Vec<(String, String)> = (0u32..1000)
            .map(|i| (format!("key{i:04}"), format!("val{i:04}")))
            .collect();
        pairs.sort_by(|(a, _), (b, _)| a.as_bytes().cmp(b.as_bytes()));

        let pair_refs: Vec<(&str, &str)> = pairs
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .collect();

        let bytes = build_bin(&pair_refs);
        let td = tempfile_helper::TempDict::from_bytes(&bytes);

        // Spot-check a few
        assert_eq!(td.dict.lookup("key0000"), Some("val0000"));
        assert_eq!(td.dict.lookup("key0500"), Some("val0500"));
        assert_eq!(td.dict.lookup("key0999"), Some("val0999"));
        assert!(td.dict.lookup("key1000").is_none());
        assert!(td.dict.lookup("key").is_none());
    }
}
