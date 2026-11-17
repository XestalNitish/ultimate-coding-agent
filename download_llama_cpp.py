"""llama.cpp ka ready binary (llama-server) download karke ./llama.cpp/ me kholta hai.

    python download_llama_cpp.py                 # auto: NVIDIA mile to cuda, warna cpu
    python download_llama_cpp.py --flavor cpu    # cpu | cuda | vulkan
    python download_llama_cpp.py --list          # release ki saari files dikhao

Agar asset naam match na ho to https://github.com/ggml-org/llama.cpp/releases se zip
haath se download karke ./llama.cpp/ me extract kar do (ya LLAMA_SERVER env set karo).
"""
import argparse
import os
import platform
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import requests

import config as C

API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
DEST = C.ROOT / "llama.cpp"


def has_nvidia() -> bool:
    return shutil.which("nvidia-smi") is not None


def classify(name: str) -> str:
    n = name.lower()
    if "cudart" in n:
        return "cudart"
    for tag in ("cuda", "vulkan", "hip", "sycl", "opencl", "kleidiai", "openvino", "rocm"):
        if tag in n:
            return tag
    return "cpu"


def platform_tag() -> list[str]:
    s = platform.system().lower()
    m = platform.machine().lower()
    arm = "arm" in m or "aarch" in m
    if s == "windows":
        return ["win", "arm64" if arm else "x64"]
    if s == "darwin":
        return ["macos", "arm64" if arm else "x64"]
    return ["ubuntu", "arm64" if arm else "x64"]


def pick_assets(assets: list[dict], flavor: str) -> list[dict]:
    tags = platform_tag()
    ok = [a for a in assets
          if a["name"].lower().endswith((".zip", ".tar.gz"))
          and "bin" in a["name"].lower()
          and all(t in a["name"].lower() for t in tags)]
    main = [a for a in ok if classify(a["name"]) == flavor]
    if flavor == "cuda":
        # purane 2GB NVIDIA cards ke liye CUDA 12.x safe hai (13.x purane GPUs drop karta hai)
        def key(a):
            v = [int(x) for x in re.findall(r"\d+", a["name"].split("cuda")[-1])[:2]] + [0, 0]
            return (v[0] == 12, v[0], v[1])
        main.sort(key=key, reverse=True)
    if not main:
        return []
    chosen = [main[0]]
    if flavor == "cuda" and platform.system().lower() == "windows":
        ver = re.search(r"cuda-?([\d.]+)", main[0]["name"].lower())
        for a in ok:
            if classify(a["name"]) == "cudart" and (not ver or ver.group(1) in a["name"].lower()):
                chosen.append(a)
                break
    return chosen


def download(url: str, out: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(out, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="", flush=True)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flavor", choices=["cpu", "cuda", "vulkan"], default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    try:
        rel = requests.get(API, timeout=30).json()
        assets = rel["assets"]
    except Exception as e:
        print(f"GitHub API fail: {e}\nManual: https://github.com/ggml-org/llama.cpp/releases")
        return 1
    print(f"llama.cpp release: {rel.get('tag_name')}")
    if args.list:
        for a in assets:
            print(" ", a["name"], f"({a['size'] // 1_000_000} MB)")
        return 0

    flavor = args.flavor or ("cuda" if has_nvidia() else "cpu")
    chosen = pick_assets(assets, flavor)
    if not chosen and flavor != "cpu":
        print(f"{flavor} build nahi mila, cpu try karta hoon")
        chosen = pick_assets(assets, "cpu")
    if not chosen:
        print("Match nahi mila. `--list` se naam dekho aur manual download karo.")
        return 1

    DEST.mkdir(parents=True, exist_ok=True)
    for a in chosen:
        print(f"download: {a['name']}")
        tmp = DEST / a["name"]
        download(a["browser_download_url"], tmp)
        shutil.unpack_archive(str(tmp), str(DEST))
        tmp.unlink(missing_ok=True)

    exe = next((p for p in DEST.rglob("llama-server*") if p.is_file() and p.suffix in ("", ".exe")), None)
    if not exe:
        print("llama-server nahi mila extract ke baad; ./llama.cpp/ khud check karo.")
        return 1
    if os.name != "nt":
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    print(f"ready: {exe}")
    print("Check:", exe, "--version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
