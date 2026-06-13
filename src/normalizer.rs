/// Text normalizer — expands Arabic/full-width digits, dates, years, percent,
/// measurement units, and currency into Chinese character form before G2P lookup.
///
/// Pipeline position: normalize(text) → segment → lookup → jyutping
///
/// Rules applied (scan order, first match wins per token):
///   ¥/€/£/₩/￥ + N    → cardinal(N) + currency name
///   HK$N / $N          → cardinal(N) + 元
///   USD/EUR/GBP/… + N  → cardinal(N) + currency name
///   N<unit>            → cardinal(N) + unit  (km/h→公里每小時, °C→攝氏度, kg→公斤…)
///   N.M<unit>          → decimal(N.M) + unit
///   N%                 → 百分之 + cardinal(N)
///   N.M%               → 百分之 + decimal(N.M)
///   N年                → digits-to-chars (year, digit-by-digit)
///   standalone 4-digit 1000–2999 → digits-to-chars (year heuristic)
///   N月/N日/N號/N時/N點/N分/N秒 → cardinal(N)
///   7+ digit run       → digits-to-chars (phone number)
///   else               → cardinal(N)

/// Punctuation normaliser — run BEFORE `normalize()` in the pipeline.
///
/// Transforms exotic / TTS-unfriendly punctuation into plain Cantonese
/// equivalents that the G2P lookup can handle cleanly:
///
/// | Input | Output | Notes |
/// |---|---|---|
/// | `「」『』【】《》〈〉〔〕` | (removed) | Quotation / bracket marks |
/// | `""''` | (removed) | Curly quotes |
/// | `…` / `……` / `...` | `。` | Ellipsis → full stop |
/// | `——` / `—` / `–` | `，` | Em/en dash → comma pause |
/// | `--` | `，` | ASCII double-hyphen → comma pause |
/// | `·` `・` `•` | ` ` | Middle dot → space |
/// | `～` `〜` | ` ` | Wave dash → space |
/// | `、` | `，` | Enumeration comma → comma |
/// | `※★☆□■△▲▽▼○●◎◆◇` | (removed) | Decorative symbols |
/// | Multiple spaces | single space | Collapse whitespace |
pub fn punc_norm(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let n = chars.len();
    let mut out = String::with_capacity(n);
    let mut i = 0;
    let mut last_space = false;

    while i < n {
        let c = chars[i];
        match c {
            // Quotation / bracket marks — remove
            '「' | '」' | '『' | '』' |
            '【' | '】' | '《' | '》' | '〈' | '〉' | '〔' | '〕' |
            '\u{201C}' | '\u{201D}' | '\u{2018}' | '\u{2019}' => {
                last_space = false;
                i += 1;
            }
            // Ellipsis → full stop (consume consecutive)
            '…' => {
                while i + 1 < n && chars[i + 1] == '…' { i += 1; }
                out.push('。');
                last_space = false;
                i += 1;
            }
            // ASCII triple-dot → full stop (consume all trailing dots)
            '.' if i + 2 < n && chars[i + 1] == '.' && chars[i + 2] == '.' => {
                while i + 1 < n && chars[i + 1] == '.' { i += 1; }
                out.push('。');
                last_space = false;
                i += 1;
            }
            // Em dash (single or paired ——) → comma pause
            '—' => {
                if i + 1 < n && chars[i + 1] == '—' { i += 1; }
                out.push('，');
                last_space = false;
                i += 1;
            }
            // En dash → comma pause
            '–' => {
                out.push('，');
                last_space = false;
                i += 1;
            }
            // Double hyphen → comma pause; single hyphen kept (units: km/h, dates)
            '-' if i + 1 < n && chars[i + 1] == '-' => {
                i += 2;
                out.push('，');
                last_space = false;
            }
            // Middle dots → space
            '·' | '・' | '•' | '\u{2027}' => {
                if !last_space { out.push(' '); last_space = true; }
                i += 1;
            }
            // Wave dash → space
            '～' | '〜' => {
                if !last_space { out.push(' '); last_space = true; }
                i += 1;
            }
            // Enumeration comma → full-width comma
            '、' => {
                out.push('，');
                last_space = false;
                i += 1;
            }
            // Decorative symbols → remove
            '※' | '★' | '☆' | '□' | '■' | '△' | '▲' | '▽' | '▼' |
            '○' | '●' | '◎' | '◆' | '◇' => {
                last_space = false;
                i += 1;
            }
            // Whitespace — collapse consecutive runs
            ' ' | '\t' => {
                if !last_space { out.push(' '); last_space = true; }
                i += 1;
            }
            _ => {
                out.push(c);
                last_space = false;
                i += 1;
            }
        }
    }
    out
}

pub fn normalize(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let n = chars.len();
    let mut out = String::with_capacity(n * 2);
    let mut i = 0;

    while i < n {
        // ── Currency symbol prefixes: ¥ € £ ₩ ￥ ────────────────────────
        if let Some((ccy, sym_len)) = match_currency_symbol(&chars, i) {
            let j = i + sym_len;
            let k = if chars.get(j) == Some(&' ') { j + 1 } else { j };
            if let Some((num_str, num_len)) = scan_number(&chars, k) {
                out.push_str(&expand_number(&num_str));
                out.push_str(ccy);
                i = k + num_len;
                continue;
            }
            // no digit follows — fall through to char-by-char
        }

        // ── HK$ prefix ──────────────────────────────────────────────────
        if i + 2 < n && chars[i] == 'H' && chars[i + 1] == 'K' && chars[i + 2] == '$' {
            if let Some((num_str, num_len)) = scan_number(&chars, i + 3) {
                out.push_str(&expand_number(&num_str));
                out.push('元');
                i += 3 + num_len;
                continue;
            }
            out.push_str("HK$");
            i += 3;
            continue;
        }

        // ── $ prefix ────────────────────────────────────────────────────
        if chars[i] == '$' {
            if let Some((num_str, num_len)) = scan_number(&chars, i + 1) {
                out.push_str(&expand_number(&num_str));
                out.push('元');
                i += 1 + num_len;
                continue;
            }
            out.push('$');
            i += 1;
            continue;
        }

        // ── 3-letter currency code prefixes: USD EUR GBP etc. ───────────
        if let Some((ccy, code_len)) = match_currency_code(&chars, i) {
            let j = i + code_len;
            let k = if chars.get(j) == Some(&' ') { j + 1 } else { j };
            if let Some((num_str, num_len)) = scan_number(&chars, k) {
                out.push_str(&expand_number(&num_str));
                out.push_str(ccy);
                i = k + num_len;
                continue;
            }
            // no digit follows — fall through
        }

        // ── Digit run (integer or decimal) ──────────────────────────────
        if to_ascii_digit(chars[i]).is_some() {
            if let Some((num_str, num_len)) = scan_number(&chars, i) {
                let j = i + num_len;
                // allow one optional space before unit suffix
                let k = if chars.get(j) == Some(&' ') { j + 1 } else { j };
                // unit suffix takes priority over context suffixes
                if let Some((unit, unit_len)) = match_unit(&chars, k) {
                    out.push_str(&expand_number(&num_str));
                    out.push_str(unit);
                    i = k + unit_len;
                    continue;
                }
                let next = chars.get(j).copied();
                if num_str.contains('.') {
                    // decimal — handle % context; otherwise plain expansion
                    if next == Some('%') || next == Some('％') {
                        out.push_str("百分之");
                        out.push_str(&expand_number(&num_str));
                        i = j + 1;
                    } else {
                        out.push_str(&expand_number(&num_str));
                        i = j;
                    }
                } else {
                    // integer — use context-sensitive rules (year/date/phone/etc.)
                    let expanded = expand_digits(&num_str, next);
                    out.push_str(&expanded);
                    if next == Some('%') || next == Some('％') {
                        i = j + 1;
                    } else {
                        i = j;
                    }
                }
                continue;
            }
        }

        out.push(chars[i]);
        i += 1;
    }

    out
}

// ── Unit suffix matching ─────────────────────────────────────────────────────

/// Match a measurement unit suffix at `chars[start..]`.
/// Units are checked longest-first to avoid partial matches (e.g. "km" before "m").
/// Returns `(cantonese_expansion, chars_consumed)`.
fn match_unit(chars: &[char], start: usize) -> Option<(&'static str, usize)> {
    // Ordered longest-first within each ambiguous group.
    static UNITS: &[(&str, &str)] = &[
        // speed (must precede km/m)
        ("km/h", "公里每小時"),
        ("m/s",  "米每秒"),
        ("mph",  "英里每小時"),
        // area (must precede km/m/cm/mm)
        ("km²",  "平方公里"),
        ("cm²",  "平方厘米"),
        ("mm²",  "平方毫米"),
        ("m²",   "平方米"),
        // energy/power (must precede kW/W)
        ("kWh",  "千瓦時"),
        ("kW",   "千瓦"),
        // distance
        ("km",   "公里"),
        ("cm",   "厘米"),
        ("mm",   "毫米"),
        // mass (must precede g)
        ("mg",   "毫克"),
        ("kg",   "公斤"),
        // volume (must precede L/l)
        ("mL",   "毫升"),
        ("ml",   "毫升"),
        // temperature — two-char °C/°F must precede single-char fallbacks
        ("°C",   "攝氏度"),
        ("°F",   "華氏度"),
        ("℃",   "攝氏度"),   // U+2103
        ("℉",   "華氏度"),   // U+2109
        // Unicode unit symbols
        ("㎞",  "公里"),     // U+339E
        ("㎡",  "平方米"),   // U+33A1
        // single-char units (must come last)
        ("m",    "米"),
        ("g",    "克"),
        ("W",    "瓦特"),
        ("L",    "公升"),
        ("l",    "公升"),
    ];
    for &(unit, expansion) in UNITS {
        let uc: Vec<char> = unit.chars().collect();
        let len = uc.len();
        if start + len > chars.len() {
            continue;
        }
        if &chars[start..start + len] != uc.as_slice() {
            continue;
        }
        // Unit must not be followed by an ASCII letter (prevents "kg" matching "kgf")
        if chars.get(start + len).map(|c| c.is_ascii_alphabetic()).unwrap_or(false) {
            continue;
        }
        return Some((expansion, len));
    }
    None
}

// ── Currency matching ────────────────────────────────────────────────────────

/// Match a single-character currency symbol prefix.
fn match_currency_symbol(chars: &[char], pos: usize) -> Option<(&'static str, usize)> {
    static SYMBOLS: &[(char, &str)] = &[
        ('€',  "歐元"),    // U+20AC
        ('£',  "英鎊"),    // U+00A3
        ('₩',  "韓圓"),    // U+20A9
        ('￥', "人民幣"),   // U+FFE5 full-width yen → CNY in HK context
        ('¥',  "日圓"),    // U+00A5 yen sign → JPY in HK context
    ];
    let c = *chars.get(pos)?;
    SYMBOLS.iter().find(|&&(sym, _)| c == sym).map(|&(_, exp)| (exp, 1))
}

/// Match a 3-letter (or longer) ISO currency code prefix (USD, EUR, etc.).
fn match_currency_code(chars: &[char], pos: usize) -> Option<(&'static str, usize)> {
    static CODES: &[(&str, &str)] = &[
        ("AUD",  "澳元"),
        ("CAD",  "加元"),
        ("CNY",  "人民幣"),
        ("EUR",  "歐元"),
        ("GBP",  "英鎊"),
        ("JPY",  "日圓"),
        ("KRW",  "韓圓"),
        ("MYR",  "令吉"),
        ("RMB",  "人民幣"),
        ("SGD",  "坡元"),
        ("THB",  "泰銖"),
        ("TWD",  "新台幣"),
        ("USD",  "美元"),
    ];
    for &(code, expansion) in CODES {
        let cc: Vec<char> = code.chars().collect();
        let len = cc.len();
        if pos + len > chars.len() {
            continue;
        }
        if &chars[pos..pos + len] != cc.as_slice() {
            continue;
        }
        // Code must not be followed by another ASCII letter (prevents "USDT" → USD)
        if chars.get(pos + len).map(|c| c.is_ascii_alphabetic()).unwrap_or(false) {
            continue;
        }
        return Some((expansion, len));
    }
    None
}

// ── Number scanning ──────────────────────────────────────────────────────────

/// Scan an integer or decimal number starting at `start`.
/// Handles full-width digits (０-９) and optional decimal part (`digits . digits`).
/// Returns `(number_string, chars_consumed)` where `number_string` uses ASCII digits.
fn scan_number(chars: &[char], start: usize) -> Option<(String, usize)> {
    let mut s = String::new();
    let mut i = start;
    // integer part
    while i < chars.len() {
        if let Some(d) = to_ascii_digit(chars[i]) {
            s.push(d);
            i += 1;
        } else {
            break;
        }
    }
    if s.is_empty() {
        return None;
    }
    // optional decimal part: '.' followed by at least one digit
    if chars.get(i) == Some(&'.') {
        if let Some(&next) = chars.get(i + 1) {
            if to_ascii_digit(next).is_some() {
                s.push('.');
                i += 1; // consume '.'
                while i < chars.len() {
                    if let Some(d) = to_ascii_digit(chars[i]) {
                        s.push(d);
                        i += 1;
                    } else {
                        break;
                    }
                }
            }
        }
    }
    Some((s, i - start))
}

/// Expand a number string (integer or decimal) to Cantonese, ignoring context.
/// `"36.5"` → `"三十六點五"`, `"100"` → `"一百"`.
fn expand_number(num_str: &str) -> String {
    if let Some(dot) = num_str.find('.') {
        let int_val: u64 = num_str[..dot].parse().unwrap_or(0);
        let frac = &num_str[dot + 1..];
        let mut s = cardinal(int_val);
        s.push('點');
        s.push_str(&digits_to_chars(frac));
        return s;
    }
    if let Ok(v) = num_str.parse::<u64>() {
        return cardinal(v);
    }
    digits_to_chars(num_str)
}

// ── Legacy helpers (kept for context-sensitive integer expansion) ────────────

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
            if lo < 10_000_000 { s.push('零'); }
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
            if lo < 1_000 { s.push('零'); }
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
            if rem < 100 { s.push('零'); }
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
            if rem < 10 { s.push('零'); }
            s.push_str(&cardinal_inner(rem, false));
        }
        return s;
    }

    // 十 (10)
    if n >= 10 {
        let tens = (n / 10) as usize;
        let ones = (n % 10) as usize;
        let mut s = String::new();
        if tens > 1 || !top { s.push(D[tens]); }
        s.push('十');
        if ones > 0 { s.push(D[ones]); }
        return s;
    }

    D[n as usize].to_string()
}

// ── Rust unit tests ─────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ── cardinal ─────────────────────────────────────────────────────────────
    #[test] fn card_zero()    { assert_eq!(cardinal(0),      "零"); }
    #[test] fn card_one()     { assert_eq!(cardinal(1),      "一"); }
    #[test] fn card_ten()     { assert_eq!(cardinal(10),     "十"); }
    #[test] fn card_eleven()  { assert_eq!(cardinal(11),     "十一"); }
    #[test] fn card_twenty()  { assert_eq!(cardinal(20),     "二十"); }
    #[test] fn card_hundred() { assert_eq!(cardinal(100),    "一百"); }
    #[test] fn card_110()     { assert_eq!(cardinal(110),    "一百一十"); }
    #[test] fn card_103()     { assert_eq!(cardinal(103),    "一百零三"); }
    #[test] fn card_1000()    { assert_eq!(cardinal(1000),   "一千"); }
    #[test] fn card_1010()    { assert_eq!(cardinal(1010),   "一千零一十"); }
    #[test] fn card_1001()    { assert_eq!(cardinal(1001),   "一千零一"); }
    #[test] fn card_1100()    { assert_eq!(cardinal(1100),   "一千一百"); }
    #[test] fn card_12345()   { assert_eq!(cardinal(12345),  "一萬二千三百四十五"); }

    // ── digits_to_chars ───────────────────────────────────────────────────────
    #[test] fn dtc_year()     { assert_eq!(digits_to_chars("2026"), "二零二六"); }
    #[test] fn dtc_1997()     { assert_eq!(digits_to_chars("1997"), "一九九七"); }

    // ── expand_number (decimal) ───────────────────────────────────────────────
    #[test] fn expand_decimal()      { assert_eq!(expand_number("36.5"),  "三十六點五"); }
    #[test] fn expand_decimal_zero() { assert_eq!(expand_number("0.5"),   "零點五"); }
    #[test] fn expand_decimal_two()  { assert_eq!(expand_number("3.14"),  "三點一四"); }
    #[test] fn expand_integer()      { assert_eq!(expand_number("100"),   "一百"); }

    // ── normalize: existing rules (regression) ────────────────────────────────
    #[test] fn norm_year_suffix()  { assert_eq!(normalize("2026年"),    "二零二六年"); }
    #[test] fn norm_year_standalone() { assert_eq!(normalize("1997"),   "一九九七"); }
    #[test] fn norm_date()         { assert_eq!(normalize("6月13日"),   "六月十三日"); }
    #[test] fn norm_date_full()    { assert_eq!(normalize("2026年6月13日"), "二零二六年六月十三日"); }
    #[test] fn norm_percent()      { assert_eq!(normalize("50%"),        "百分之五十"); }
    #[test] fn norm_fullwidth()    { assert_eq!(normalize("２０２６年"), "二零二六年"); }
    #[test] fn norm_phone()        { assert_eq!(normalize("98765432"),   "九八七六五四三二"); }
    #[test] fn norm_hkd()          { assert_eq!(normalize("HK$100"),     "一百元"); }
    #[test] fn norm_dollar()       { assert_eq!(normalize("$50"),        "五十元"); }
    #[test] fn norm_passthrough()  { assert_eq!(normalize("你好嘅"),     "你好嘅"); }
    #[test] fn norm_mixed()        { assert_eq!(normalize("今日係2026年6月13日"), "今日係二零二六年六月十三日"); }
    #[test] fn norm_time()         { assert_eq!(normalize("下午3時15分"), "下午三時十五分"); }
    #[test] fn norm_cardinal_small() { assert_eq!(normalize("有3個人"),  "有三個人"); }
    #[test] fn norm_month_dec()    { assert_eq!(normalize("12月25日"),   "十二月二十五日"); }

    // ── normalize: decimal numbers ────────────────────────────────────────────
    #[test] fn norm_decimal_plain()   { assert_eq!(normalize("3.14"),   "三點一四"); }
    #[test] fn norm_decimal_percent() { assert_eq!(normalize("50.5%"),  "百分之五十點五"); }
    #[test] fn norm_hkd_decimal()     { assert_eq!(normalize("HK$3.50"), "三點五零元"); }

    // ── normalize: measurement units ─────────────────────────────────────────
    #[test] fn norm_unit_kmh()     { assert_eq!(normalize("120km/h"),   "一百二十公里每小時"); }
    #[test] fn norm_unit_kmh_sp()  { assert_eq!(normalize("120 km/h"),  "一百二十公里每小時"); }
    #[test] fn norm_unit_celsius() { assert_eq!(normalize("36.5°C"),    "三十六點五攝氏度"); }
    #[test] fn norm_unit_cel_int() { assert_eq!(normalize("36°C"),      "三十六攝氏度"); }
    #[test] fn norm_unit_cel_uni() { assert_eq!(normalize("36.5℃"),    "三十六點五攝氏度"); }
    #[test] fn norm_unit_fahrenheit() { assert_eq!(normalize("98.6°F"), "九十八點六華氏度"); }
    #[test] fn norm_unit_kg()      { assert_eq!(normalize("75kg"),      "七十五公斤"); }
    #[test] fn norm_unit_km()      { assert_eq!(normalize("100km"),     "一百公里"); }
    #[test] fn norm_unit_cm()      { assert_eq!(normalize("180cm"),     "一百八十厘米"); }
    #[test] fn norm_unit_m()       { assert_eq!(normalize("1.8m"),      "一點八米"); }
    #[test] fn norm_unit_m2()      { assert_eq!(normalize("3m²"),       "三平方米"); }
    #[test] fn norm_unit_ml()      { assert_eq!(normalize("250ml"),     "二百五十毫升"); }
    #[test] fn norm_unit_litre()   { assert_eq!(normalize("1.5L"),      "一點五公升"); }
    #[test] fn norm_unit_g()       { assert_eq!(normalize("200g"),      "二百克"); }
    #[test] fn norm_unit_mg()      { assert_eq!(normalize("500mg"),     "五百毫克"); }
    #[test] fn norm_unit_kw()      { assert_eq!(normalize("5kW"),       "五千瓦"); }
    #[test] fn norm_unit_kwh()     { assert_eq!(normalize("100kWh"),    "一百千瓦時"); }
    #[test] fn norm_unit_mph()     { assert_eq!(normalize("60mph"),     "六十英里每小時"); }
    #[test] fn norm_unit_ms()      { assert_eq!(normalize("10m/s"),     "十米每秒"); }
    #[test] fn norm_unit_in_sent() { assert_eq!(normalize("速度係120km/h"), "速度係一百二十公里每小時"); }
    #[test] fn norm_unit_cel_sent(){ assert_eq!(normalize("氣溫36.5°C"), "氣溫三十六點五攝氏度"); }

    // ── normalize: currency ───────────────────────────────────────────────────
    #[test] fn norm_usd()    { assert_eq!(normalize("USD100"),  "一百美元"); }
    #[test] fn norm_eur()    { assert_eq!(normalize("EUR200"),  "二百歐元"); }
    #[test] fn norm_gbp()    { assert_eq!(normalize("GBP50"),   "五十英鎊"); }
    #[test] fn norm_rmb()    { assert_eq!(normalize("RMB500"),  "五百人民幣"); }
    #[test] fn norm_yen_sym(){ assert_eq!(normalize("¥500"),    "五百日圓"); }
    #[test] fn norm_eur_sym(){ assert_eq!(normalize("€100"),    "一百歐元"); }
    #[test] fn norm_gbp_sym(){ assert_eq!(normalize("£80"),     "八十英鎊"); }
    #[test] fn norm_rmb_sym(){ assert_eq!(normalize("￥200"),   "二百人民幣"); }
    #[test] fn norm_usd_sp() { assert_eq!(normalize("USD 100"), "一百美元"); }

    // ── punc_norm ─────────────────────────────────────────────────────────────
    #[test] fn pn_quotebrackets()  { assert_eq!(punc_norm("「你好」"),         "你好"); }
    #[test] fn pn_book_title()     { assert_eq!(punc_norm("《天氣之子》"),      "天氣之子"); }
    #[test] fn pn_square()         { assert_eq!(punc_norm("【重要】"),          "重要"); }
    #[test] fn pn_curly_quotes()   { assert_eq!(punc_norm("\u{201C}hello\u{201D}"), "hello"); }
    #[test] fn pn_ellipsis()       { assert_eq!(punc_norm("好吧…"),            "好吧。"); }
    #[test] fn pn_double_ellipsis(){ assert_eq!(punc_norm("好吧……"),           "好吧。"); }
    #[test] fn pn_ascii_ellipsis() { assert_eq!(punc_norm("好吧..."),          "好吧。"); }
    #[test] fn pn_em_dash_pair()   { assert_eq!(punc_norm("一——二"),            "一，二"); }
    #[test] fn pn_em_dash_single() { assert_eq!(punc_norm("一—二"),             "一，二"); }
    #[test] fn pn_en_dash()        { assert_eq!(punc_norm("一–二"),             "一，二"); }
    #[test] fn pn_double_hyphen()  { assert_eq!(punc_norm("一--二"),            "一，二"); }
    #[test] fn pn_single_hyphen()  { assert_eq!(punc_norm("km-h"),             "km-h"); }
    #[test] fn pn_middle_dot()     { assert_eq!(punc_norm("奧斯卡·王爾德"),    "奧斯卡 王爾德"); }
    #[test] fn pn_wave_dash()      { assert_eq!(punc_norm("早～"),              "早 "); }
    #[test] fn pn_enum_comma()     { assert_eq!(punc_norm("蘋果、橙"),          "蘋果，橙"); }
    #[test] fn pn_decorative()     { assert_eq!(punc_norm("※注意★"),           "注意"); }
    #[test] fn pn_multi_space()    { assert_eq!(punc_norm("你  好"),            "你 好"); }
    #[test] fn pn_passthrough()    { assert_eq!(punc_norm("你好嘅，I love HK"), "你好嘅，I love HK"); }
    #[test] fn pn_combined()       {
        // Typical messy TTS input
        assert_eq!(
            punc_norm("《天氣之子》——一個關於天氣……的故事"),
            "天氣之子，一個關於天氣。的故事"
        );
    }
}
