/// Text normalizer — expands Arabic/full-width digits, dates, years, percent
/// into Chinese character form before segmentation + G2P lookup.
///
/// Pipeline position: normalize(text) → segment → lookup → jyutping
///
/// Rules applied (in scan order, first match wins per digit run):
///   HK$N / $N          → cardinal(N) + 元
///   N% / N％           → 百分之 + cardinal(N)
///   N年                → digits-to-chars (year, digit-by-digit)
///   standalone 4-digit 1000-2999 → digits-to-chars (year heuristic)
///   N月                → cardinal(N)  (month)
///   N日 / N號          → cardinal(N)  (day/date)
///   N時 / N點          → cardinal(N)  (hour)
///   N分 / N秒          → cardinal(N)  (minute/second)
///   7+ digit run       → digits-to-chars  (phone number)
///   else               → cardinal(N)

pub fn normalize(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let n = chars.len();
    let mut out = String::with_capacity(n * 2);
    let mut i = 0;

    while i < n {
        // ── HK$ prefix ──────────────────────────────────────────────────
        if i + 2 < n && chars[i] == 'H' && chars[i + 1] == 'K' && chars[i + 2] == '$' {
            if let Some((dig, len)) = scan_digits(&chars, i + 3) {
                if let Ok(v) = dig.parse::<u64>() {
                    out.push_str(&cardinal(v));
                    out.push('元');
                    i += 3 + len;
                    continue;
                }
            }
            out.push_str("HK$");
            i += 3;
            continue;
        }

        // ── $ prefix ────────────────────────────────────────────────────
        if chars[i] == '$' {
            if let Some((dig, len)) = scan_digits(&chars, i + 1) {
                if let Ok(v) = dig.parse::<u64>() {
                    out.push_str(&cardinal(v));
                    out.push('元');
                    i += 1 + len;
                    continue;
                }
            }
            out.push('$');
            i += 1;
            continue;
        }

        // ── digit run (ASCII 0-9 or full-width ０-９) ────────────────────
        if to_ascii_digit(chars[i]).is_some() {
            let mut digits = String::new();
            while i < n {
                if let Some(d) = to_ascii_digit(chars[i]) {
                    digits.push(d);
                    i += 1;
                } else {
                    break;
                }
            }
            let next = chars.get(i).copied();
            let expanded = expand_digits(&digits, next);
            out.push_str(&expanded);
            // consume the trailing % / ％ — already factored into expansion
            if next == Some('%') || next == Some('％') {
                i += 1;
            }
            continue;
        }

        out.push(chars[i]);
        i += 1;
    }

    out
}

// ── internal helpers ────────────────────────────────────────────────────────

fn to_ascii_digit(c: char) -> Option<char> {
    if c.is_ascii_digit() {
        return Some(c);
    }
    // full-width digits ０ (U+FF10) … ９ (U+FF19)
    let u = c as u32;
    if (0xFF10..=0xFF19).contains(&u) {
        return char::from_u32(u - 0xFF10 + b'0' as u32);
    }
    None
}

fn scan_digits(chars: &[char], start: usize) -> Option<(String, usize)> {
    let mut s = String::new();
    let mut i = start;
    while i < chars.len() {
        if let Some(d) = to_ascii_digit(chars[i]) {
            s.push(d);
            i += 1;
        } else {
            break;
        }
    }
    if s.is_empty() { None } else { Some((s, i - start)) }
}

fn expand_digits(digits: &str, next: Option<char>) -> String {
    // percent
    if next == Some('%') || next == Some('％') {
        if let Ok(v) = digits.parse::<u64>() {
            return format!("百分之{}", cardinal(v));
        }
    }
    // year context
    if next == Some('年') {
        return digits_to_chars(digits);
    }
    // date/time suffixes → cardinal
    if matches!(next, Some('月') | Some('日') | Some('號') | Some('時') | Some('點') | Some('分') | Some('秒')) {
        if let Ok(v) = digits.parse::<u64>() {
            return cardinal(v);
        }
    }
    // standalone 4-digit year heuristic (1000–2999)
    if digits.len() == 4 {
        if let Ok(v) = digits.parse::<u32>() {
            if (1000..=2999).contains(&v) {
                return digits_to_chars(digits);
            }
        }
    }
    // phone / long number → digit-by-digit
    if digits.len() >= 7 {
        return digits_to_chars(digits);
    }
    // default → cardinal
    if let Ok(v) = digits.parse::<u64>() {
        cardinal(v)
    } else {
        digits_to_chars(digits)
    }
}

/// Digit-by-digit: "2026" → "二零二六"
fn digits_to_chars(digits: &str) -> String {
    digits
        .chars()
        .map(|d| match d {
            '0' => '零',
            '1' => '一',
            '2' => '二',
            '3' => '三',
            '4' => '四',
            '5' => '五',
            '6' => '六',
            '7' => '七',
            '8' => '八',
            '9' => '九',
            c => c,
        })
        .collect()
}

/// Cantonese place-value cardinal (0 – 9,999,999,999).
///
/// Special forms:
///   0           → 零
///   10–19       → 十 十一 … 十九  (no leading 一 at top level)
///   100+        → 一百一十  (一 restored in sub-position)
///   zero gap    → 一百零三, 一千零一十 (零 placeholder)
pub fn cardinal(n: u64) -> String {
    cardinal_inner(n, true)
}

fn cardinal_inner(n: u64, top: bool) -> String {
    if n == 0 {
        return "零".to_string();
    }

    const D: [char; 10] = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];

    // 億 (100,000,000)
    if n >= 100_000_000 {
        let hi = n / 100_000_000;
        let lo = n % 100_000_000;
        let mut s = cardinal_inner(hi, false);
        s.push('億');
        if lo > 0 {
            if lo < 10_000_000 {
                s.push('零');
            }
            s.push_str(&cardinal_inner(lo, false));
        }
        return s;
    }

    // 萬 (10,000)
    if n >= 10_000 {
        let hi = n / 10_000;
        let lo = n % 10_000;
        let mut s = cardinal_inner(hi, false);
        s.push('萬');
        if lo > 0 {
            if lo < 1_000 {
                s.push('零');
            }
            s.push_str(&cardinal_inner(lo, false));
        }
        return s;
    }

    // 千 (1,000)
    if n >= 1_000 {
        let d = (n / 1_000) as usize;
        let rem = n % 1_000;
        let mut s = format!("{}千", D[d]);
        if rem > 0 {
            if rem < 100 {
                s.push('零');
            }
            s.push_str(&cardinal_inner(rem, false));
        }
        return s;
    }

    // 百 (100)
    if n >= 100 {
        let d = (n / 100) as usize;
        let rem = n % 100;
        let mut s = format!("{}百", D[d]);
        if rem > 0 {
            if rem < 10 {
                s.push('零');
            }
            s.push_str(&cardinal_inner(rem, false));
        }
        return s;
    }

    // 十 (10)
    if n >= 10 {
        let tens = (n / 10) as usize;
        let ones = (n % 10) as usize;
        let mut s = String::new();
        // Only omit the leading 一 at top-level for 10–19
        if tens > 1 || !top {
            s.push(D[tens]);
        }
        s.push('十');
        if ones > 0 {
            s.push(D[ones]);
        }
        return s;
    }

    D[n as usize].to_string()
}

// ── Rust unit tests ─────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // cardinal
    #[test] fn card_zero()  { assert_eq!(cardinal(0),  "零"); }
    #[test] fn card_one()   { assert_eq!(cardinal(1),  "一"); }
    #[test] fn card_ten()   { assert_eq!(cardinal(10), "十"); }
    #[test] fn card_eleven(){ assert_eq!(cardinal(11), "十一"); }
    #[test] fn card_twenty(){ assert_eq!(cardinal(20), "二十"); }
    #[test] fn card_hundred(){ assert_eq!(cardinal(100), "一百"); }
    #[test] fn card_110()   { assert_eq!(cardinal(110), "一百一十"); }
    #[test] fn card_103()   { assert_eq!(cardinal(103), "一百零三"); }
    #[test] fn card_1000()  { assert_eq!(cardinal(1000), "一千"); }
    #[test] fn card_1010()  { assert_eq!(cardinal(1010), "一千零一十"); }
    #[test] fn card_1001()  { assert_eq!(cardinal(1001), "一千零一"); }
    #[test] fn card_1100()  { assert_eq!(cardinal(1100), "一千一百"); }
    #[test] fn card_12345() { assert_eq!(cardinal(12345), "一萬二千三百四十五"); }

    // digits_to_chars
    #[test] fn dtc_year()   { assert_eq!(digits_to_chars("2026"), "二零二六"); }
    #[test] fn dtc_1997()   { assert_eq!(digits_to_chars("1997"), "一九九七"); }

    // normalize
    #[test]
    fn norm_year_suffix() {
        assert_eq!(normalize("2026年"), "二零二六年");
    }
    #[test]
    fn norm_year_standalone() {
        assert_eq!(normalize("1997"), "一九九七");
    }
    #[test]
    fn norm_date() {
        assert_eq!(normalize("6月13日"), "六月十三日");
    }
    #[test]
    fn norm_date_full() {
        assert_eq!(normalize("2026年6月13日"), "二零二六年六月十三日");
    }
    #[test]
    fn norm_percent() {
        assert_eq!(normalize("50%"), "百分之五十");
    }
    #[test]
    fn norm_fullwidth() {
        assert_eq!(normalize("２０２６年"), "二零二六年");
    }
    #[test]
    fn norm_phone() {
        assert_eq!(normalize("98765432"), "九八七六五四三二");
    }
    #[test]
    fn norm_hkd() {
        assert_eq!(normalize("HK$100"), "一百元");
    }
    #[test]
    fn norm_dollar() {
        assert_eq!(normalize("$50"), "五十元");
    }
    #[test]
    fn norm_passthrough_hanzi() {
        assert_eq!(normalize("你好嘅"), "你好嘅");
    }
    #[test]
    fn norm_mixed() {
        // "今日係2026年6月13日" → Chinese digits expanded
        let result = normalize("今日係2026年6月13日");
        assert_eq!(result, "今日係二零二六年六月十三日");
    }
    #[test]
    fn norm_time() {
        assert_eq!(normalize("下午3時15分"), "下午三時十五分");
    }
    #[test]
    fn norm_cardinal_small() {
        // standalone small number → cardinal
        assert_eq!(normalize("有3個人"), "有三個人");
    }
    #[test]
    fn norm_month_dec() {
        assert_eq!(normalize("12月25日"), "十二月二十五日");
    }
}
