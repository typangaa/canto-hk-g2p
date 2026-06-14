---
name: Bug report
about: Report incorrect G2P output, crashes, or unexpected behaviour
labels: bug
assignees: ''
---

**Describe the bug**
A clear description of what went wrong.

**Input and expected vs actual output**
```python
from canto_hk_g2p import Pipeline
p = Pipeline()
p.convert("...")
# Expected: "..."
# Got:      "..."
```

**Environment**
- `canto-hk-g2p` version: <!-- pip show canto-hk-g2p -->
- Python version:
- OS / platform:

**Additional context**
Any other context (e.g. custom `data_dir`, `punc_norm=False`, batch usage).
