#!/usr/bin/env python3
"""
benchmark.py — canto-g2p performance benchmark

Measures tokens/sec for canto-g2p (single + batch) and optionally compares
with ToJyutping and PyCantonese if installed.

Usage:
    python3 scripts/benchmark.py
    python3 scripts/benchmark.py --passes 100
"""

import argparse
import time

# ---------------------------------------------------------------------------
# Optional comparison tools
# ---------------------------------------------------------------------------
try:
    import tojyutping
    HAS_TOJYUTPING = True
except ImportError:
    HAS_TOJYUTPING = False

try:
    import pycantonese
    HAS_PYCANTONESE = True
except ImportError:
    HAS_PYCANTONESE = False

# ---------------------------------------------------------------------------
# Benchmark corpus — 20 representative Cantonese sentences
# ---------------------------------------------------------------------------
CORPUS = [
    # Pure Cantonese
    "你好嘅，多謝晒",
    "香港係一個國際城市",
    "銀行今日係唔係開門㗎",
    # HK colloquial particles
    "噉我就唔知喇喎",
    "佢話佢唔嚟喇",
    "你喺邊度㗎",
    # English code-switching
    "佢send咗email俾我",
    "你有冇check過個file",
    "今日meeting幾點開始",
    # Numbers / dates
    "今日係2026年6月13日",
    "呢份文件有100頁",
    "聽日下午3時開會",
    # Mixed
    "I love Hong Kong，香港係我嘅家",
    "呢個app好好用，大家download喇",
    # Longer sentences
    "廣東話係香港嘅官方語言之一，全球有超過七千萬人講廣東話",
    # Additional variety
    "我哋今日去食飯，你想食咩嘢",
    "呢度嘅天氣好熱，我想飲凍嘢",
    "佢喺公司做嘢，好忙㗎",
    "你識唔識講廣東話呀",
    "香港嘅交通好方便，地鐵去到好多地方",
]

assert len(CORPUS) == 20, "Corpus must contain exactly 20 sentences"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tojyutping_convert(text: str) -> str:
    """Try known ToJyutping API variants."""
    if hasattr(tojyutping, "get_jyutping_text"):
        return tojyutping.get_jyutping_text(text)
    if hasattr(tojyutping, "add_jyutping"):
        return tojyutping.add_jyutping(text)
    # fallback: call the module as a function if callable
    raise AttributeError(
        "tojyutping: could not find get_jyutping_text or add_jyutping"
    )


def pycantonese_convert(text: str) -> str:
    """Try known PyCantonese API variants."""
    if hasattr(pycantonese, "characters_to_jyutping"):
        return str(pycantonese.characters_to_jyutping(text))
    raise AttributeError(
        "pycantonese: could not find characters_to_jyutping"
    )


def run_single(pipeline, corpus: list[str], n_passes: int) -> float:
    """Run convert() sequentially, return elapsed seconds."""
    start = time.perf_counter()
    for _ in range(n_passes):
        for text in corpus:
            pipeline.convert(text)
    return time.perf_counter() - start


def run_batch(pipeline, corpus: list[str], n_passes: int) -> float:
    """Run convert_batch() once per pass, return elapsed seconds."""
    start = time.perf_counter()
    for _ in range(n_passes):
        pipeline.convert_batch(corpus)
    return time.perf_counter() - start


def run_tool(fn, corpus: list[str], n_passes: int) -> float:
    """Run an arbitrary per-sentence callable, return elapsed seconds."""
    start = time.perf_counter()
    for _ in range(n_passes):
        for text in corpus:
            fn(text)
    return time.perf_counter() - start


def fmt_float(v: float, decimals: int = 3) -> str:
    return f"{v:.{decimals}f}"


def fmt_int(v: float) -> str:
    return f"{int(v):,}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark canto-g2p vs ToJyutping / PyCantonese"
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=50,
        metavar="N",
        help="Number of full passes through the corpus (default: 50)",
    )
    args = parser.parse_args()

    N_PASSES = args.passes
    N_WARMUP = 3
    N_SENT = len(CORPUS)
    TOTAL_SENT = N_PASSES * N_SENT

    # ------------------------------------------------------------------
    # Import canto-g2p (required)
    # ------------------------------------------------------------------
    try:
        from canto_hk_g2p import Pipeline
    except ImportError as exc:
        print(f"ERROR: could not import canto_hk_g2p: {exc}")
        print("Make sure the library is installed: pip install -e . (maturin develop)")
        raise SystemExit(1)

    pipeline = Pipeline()

    # ------------------------------------------------------------------
    # Print corpus
    # ------------------------------------------------------------------
    print()
    print("Corpus (20 sentences):")
    for i, s in enumerate(CORPUS, 1):
        display = s if len(s) <= 50 else s[:47] + "..."
        print(f"  {i:2d}. {display}")
    print()

    # ------------------------------------------------------------------
    # Warm up
    # ------------------------------------------------------------------
    print(f"Warming up ({N_WARMUP} passes) ...", end=" ", flush=True)
    for _ in range(N_WARMUP):
        for text in CORPUS:
            pipeline.convert(text)
        pipeline.convert_batch(CORPUS)
    print("done")
    print()

    # ------------------------------------------------------------------
    # Benchmarks
    # ------------------------------------------------------------------
    results: dict[str, float | None] = {}

    print(f"Running canto-g2p single ({N_PASSES} passes) ...", end=" ", flush=True)
    results["canto-g2p single"] = run_single(pipeline, CORPUS, N_PASSES)
    print("done")

    print(f"Running canto-g2p batch  ({N_PASSES} passes) ...", end=" ", flush=True)
    results["canto-g2p batch"] = run_batch(pipeline, CORPUS, N_PASSES)
    print("done")

    if HAS_TOJYUTPING:
        # Warm up
        for text in CORPUS:
            try:
                tojyutping_convert(text)
            except AttributeError:
                HAS_TOJYUTPING_FUNC = False
                break
        else:
            HAS_TOJYUTPING_FUNC = True

        if HAS_TOJYUTPING_FUNC:
            print(f"Running ToJyutping        ({N_PASSES} passes) ...", end=" ", flush=True)
            try:
                results["ToJyutping"] = run_tool(tojyutping_convert, CORPUS, N_PASSES)
                print("done")
            except Exception as exc:
                results["ToJyutping"] = None
                print(f"FAILED ({exc})")
        else:
            results["ToJyutping"] = None
    else:
        results["ToJyutping"] = None

    if HAS_PYCANTONESE:
        # Warm up
        try:
            for text in CORPUS:
                pycantonese_convert(text)
            HAS_PYCANTONESE_FUNC = True
        except Exception:
            HAS_PYCANTONESE_FUNC = False

        if HAS_PYCANTONESE_FUNC:
            print(f"Running PyCantonese       ({N_PASSES} passes) ...", end=" ", flush=True)
            try:
                results["PyCantonese"] = run_tool(pycantonese_convert, CORPUS, N_PASSES)
                print("done")
            except Exception as exc:
                results["PyCantonese"] = None
                print(f"FAILED ({exc})")
        else:
            results["PyCantonese"] = None
    else:
        results["PyCantonese"] = None

    # ------------------------------------------------------------------
    # Print table
    # ------------------------------------------------------------------
    COL_W = 22
    print()
    sep = "=" * 62
    dash = "-" * 62
    print(sep)
    print(
        f"canto-g2p benchmark  "
        f"({N_PASSES} passes × {N_SENT} sentences = {TOTAL_SENT:,} total)"
    )
    print(sep)
    header = (
        f"{'Tool':<{COL_W}}  {'Total (s)':>10}  {'Avg/sent (ms)':>13}  {'Throughput':>15}"
    )
    print(header)
    print(dash)

    not_installed_tools = {
        "ToJyutping": not HAS_TOJYUTPING,
        "PyCantonese": not HAS_PYCANTONESE,
    }

    for tool, elapsed in results.items():
        not_installed = not_installed_tools.get(tool, False)

        if not_installed:
            print(f"{'  ' + tool:<{COL_W}}  {'N/A (not installed)'}")
        elif elapsed is None:
            print(f"{'  ' + tool:<{COL_W}}  {'ERROR (see above)'}")
        else:
            avg_ms = (elapsed / TOTAL_SENT) * 1000
            throughput = TOTAL_SENT / elapsed
            print(
                f"{'  ' + tool:<{COL_W}}"
                f"  {fmt_float(elapsed):>10}"
                f"  {fmt_float(avg_ms, 3):>13}"
                f"  {fmt_int(throughput):>12} s/s"
            )

    print(sep)

    # Speedup
    single = results.get("canto-g2p single")
    batch = results.get("canto-g2p batch")
    if single and batch and batch > 0:
        speedup = single / batch
        print(f"Rayon batch speedup: {speedup:.1f}x vs single")

    print()


if __name__ == "__main__":
    main()
