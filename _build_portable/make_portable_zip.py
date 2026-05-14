"""Portable zip: source dosyalar + python_runtime/ + portable BASLAT/KURULUM."""
import os
import shutil
import sys
import zipfile
import fnmatch


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)

EXCLUDE_DIRS = {
    ".git", "__pycache__", "dist", "build", ".claude",
    "tasks", ".idea", ".vscode", ".update_tmp", ".pytest_cache",
    "_build_portable", "_server",
}
EXCLUDE_FILES = {
    ".app.pid", "account.lock", "_update.bat", "_make_zip.py",
    "BASLAT.bat", "KURULUM.bat",  # bunlar build dizininden gelecek
}
EXCLUDE_PATTERNS = ["*.pyd", "*.pyc", "*.c", "*.so", "*.exe", "*.zip"]


def should_include(rel_path: str) -> bool:
    parts = rel_path.replace(os.sep, "/").split("/")
    for p in parts[:-1]:
        if p in EXCLUDE_DIRS:
            return False
    fname = parts[-1]
    if fname in EXCLUDE_FILES:
        return False
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(fname, pat):
            return False
    return True


def main():
    # Versiyon
    with open(os.path.join(PROJECT_ROOT, "version.py"), encoding="utf-8") as f:
        version = f.read().splitlines()[0].split('"')[1]
    zip_name = f"GOLDSAM_V2_PORTABLE_v{version}.zip"
    zip_path = os.path.join(PROJECT_ROOT, zip_name)
    arcroot = "GOLDSAM_V2"
    count = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        # 1) Project source
        for root, dirs, files in os.walk(PROJECT_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, PROJECT_ROOT)
                if not should_include(rel):
                    continue
                z.write(full, f"{arcroot}/{rel.replace(os.sep, '/')}")
                count += 1

        # 2) python_runtime (içinde her şey, .pyd dahil)
        runtime_src = os.path.join(HERE, "python_runtime")
        for root, dirs, files in os.walk(runtime_src):
            # __pycache__ atla
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".pyc"):
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, runtime_src)
                arc = f"{arcroot}/python_runtime/{rel.replace(os.sep, '/')}"
                z.write(full, arc)
                count += 1

        # 3) Portable BAT'ler + vc_redist (build dir'den)
        for extra in ("BASLAT.bat", "KURULUM.bat", "TANI.bat", "vc_redist.x64.exe"):
            src = os.path.join(HERE, extra)
            if os.path.isfile(src):
                z.write(src, f"{arcroot}/{extra}")
                count += 1

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"OK: {count} dosya, {size_mb:.1f} MB -> {zip_path}")


if __name__ == "__main__":
    main()
