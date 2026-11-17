"""Open-weight GGUF models + embedding model download (resume support).

    python download_models.py              # sab
    python download_models.py --only coder main
    python download_models.py --list       # kya kitna hai dekho
"""
import argparse
import sys
import time

import config as C

MIN_BYTES = 50 * 1024 * 1024


def is_gguf(path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"GGUF"
    except OSError:
        return False


def pick_file(repo: str, quant: str) -> str | None:
    from huggingface_hub import list_repo_files
    files = [f for f in list_repo_files(repo)
             if f.lower().endswith(".gguf") and "mmproj" not in f.lower()]
    if not files:
        return None
    for q in [quant, "Q4_K_M", "Q4_K_S", "Q4_0", "Q5_K_M", "Q8_0"]:
        hit = [f for f in files if q and q.lower() in f.lower()]
        if hit:
            return sorted(hit, key=len)[0]
    print(f"  koi preferred quant nahi mila; repo me ye files hain: {files}")
    return sorted(files)[0]


def download_one(role: str) -> bool:
    real = C.real_role(role)
    if real != role:
        print(f"[{role}] {real} ka model share karta hai, alag download nahi")
        return True
    cfg = C.MODELS[role]
    path = C.model_path(role)
    if path.exists() and path.stat().st_size > MIN_BYTES and is_gguf(path):
        print(f"[{role}] already hai: {path.name} ({path.stat().st_size / 1e9:.2f} GB)")
        return True
    if cfg.get("local_path"):
        print(f"[{role}] local_path set hai par file nahi mili: {cfg['local_path']}")
        return False

    from huggingface_hub import hf_hub_download
    local_dir = C.MODELS_DIR if cfg.get("file") else C.MODELS_DIR / cfg["repo"].replace("/", "__")
    local_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 4):
        try:
            fname = cfg.get("file") or pick_file(cfg["repo"], cfg.get("quant", "Q4_K_M"))
            if not fname:
                print(f"[{role}] {cfg['repo']} me .gguf file nahi mili. Repo naam check karo "
                      f"(huggingface.co pe search karo) ya local_path do.")
                return False
            print(f"[{role}] download: {cfg['repo']} / {fname} (try {attempt}/3)")
            hf_hub_download(repo_id=cfg["repo"], filename=fname, local_dir=str(local_dir))
            path = C.model_path(role)
            if is_gguf(path):
                print(f"[{role}] OK -> {path}")
                return True
            print(f"[{role}] file GGUF nahi lag rahi, dobara try")
            path.unlink(missing_ok=True)
        except Exception as e:
            name = type(e).__name__
            print(f"[{role}] error: {name}: {e}")
            if name in ("RepositoryNotFoundError", "GatedRepoError", "RevisionNotFoundError"):
                print(f"[{role}] repo '{cfg['repo']}' nahi mila / private hai. config.py me sahi repo daalo "
                      f"ya model pehle se hai to local_path set karo.")
                return False
            time.sleep(3)
    print(f"[{role}] FAIL. config.py me repo/file check karo.")
    return False


def download_embedder() -> bool:
    try:
        from fastembed import TextEmbedding
        print(f"[embed] {C.EMBED_MODEL} download/warm-up ...")
        TextEmbedding(model_name=C.EMBED_MODEL, cache_dir=str(C.MODELS_DIR / "embed"))
        print("[embed] OK")
        return True
    except Exception as e:
        print(f"[embed] fail: {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(C.MODELS), help="sirf ye roles")
    ap.add_argument("--no-embed", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    roles = args.only or list(C.MODELS)
    if args.list:
        for r in C.MODELS:
            p = C.model_path(r)
            size = f"{p.stat().st_size / 1e9:.2f} GB" if p.exists() else "missing"
            print(f"{r:11s} port {C.MODELS[C.real_role(r)]['port']}  {p}  [{size}]")
        return 0

    ok = all([download_one(r) for r in roles])
    if not args.no_embed and not args.only:
        ok = download_embedder() and ok
    print("\nSab ready. Agla step: python start_servers.py" if ok else "\nKuch fail hua, upar dekho.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
