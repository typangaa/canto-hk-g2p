# canto-g2p

Fast Cantonese text-to-phoneme (G2P) converter — outputs **Jyutping with tone numbers** (LSHK standard, all-ASCII).

```python
from canto_g2p import Pipeline
p = Pipeline()
p.convert("你好嘅，I love Hong Kong")
# → "nei5 hou2 ge3 , I love hoeng1 gong2"   (Phase 2+)
```

**Status: Phase 0 scaffold — G2P not yet implemented.**

## Features (planned)

- Jyutping + tone numbers output (`nei5 hou2 ge3`)
- Cantonese + English code-switching (English tokens passed through in v1)
- Word-level segmentation for polyphone disambiguation
- Cantonese number/date normalization
- Rust core + Python bindings via PyO3 — zero runtime dependencies
- Rayon parallel batch processing

## Install

```bash
pip install canto-g2p          # once published
# or from source:
pip install maturin
pip install -e .
```

## Data & license

Library code: **Apache-2.0**

Bundled pronunciation data:
- [rime-cantonese](https://github.com/rime/rime-cantonese) — **CC BY 4.0** (attribution required, see NOTICE)
- [Unihan kCantonese](https://unicode.org/charts/unihan.html) — **Unicode License v3**

See [NOTICE](NOTICE) for full attribution.

## Related

- Inspiration: [SEA-G2P](https://github.com/pnnbao97/sea-g2p) (Vietnamese, Rust)
- [ToJyutping](https://github.com/CanCLID/ToJyutping) (Python/JS, BSD-2)
- [PyCantonese](https://github.com/jacksonllee/pycantonese) (Python, MIT)
