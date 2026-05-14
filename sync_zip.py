"""GOLDSAM V2 - lokal zip'i en son GitHub release ile sync et.

Kullanim:
  python sync_zip.py           # ya da sync_zip.bat (cift tikla)

Yapar:
  1. GitHub Atom feed'den latest tag'i oku (rate-limit-free)
  2. GitHub Release asset GOLDSAM_V2.zip indir
  3. Lokal'e `GOLDSAM_V2_v<tag>.zip` olarak kaydet (proje kokunde)
  4. Onceki versiyonlu zip'leri sil (sadece 1 son surum kalir)
  5. _release/OKU_BENI.txt'yi zip icine ekle (eger varsa)

Sonuc: musteriye gondereceginiz `GOLDSAM_V2_v2.x.y.zip` her zaman guncel.
"""
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ATOM_URL = "https://github.com/nurullah34/-goldsam-v2/releases.atom"
ZIP_URL = "https://github.com/nurullah34/-goldsam-v2/releases/latest/download/GOLDSAM_V2.zip"
README_PATH = ROOT / "_release" / "OKU_BENI.txt"


def latest_tag() -> str | None:
    """Atom feed'den son release tag'ini cek (API yerine — rate limit yok)."""
    try:
        req = urllib.request.Request(ATOM_URL, headers={"User-Agent": "GOLDSAM-Sync"})
        with urllib.request.urlopen(req, timeout=15) as r:
            feed = r.read().decode("utf-8")
        m = re.search(r"<title>(v\d+\.\d+\.\d+)</title>", feed)
        return m.group(1)[1:] if m else None  # "v2.1.2" → "2.1.2"
    except Exception as e:
        print(f"[HATA] Atom feed: {e}")
        return None


def download_zip(target: Path) -> bool:
    """Latest release zip'ini indir."""
    print(f"Indiriliyor: {ZIP_URL}")
    try:
        req = urllib.request.Request(
            ZIP_URL, headers={"User-Agent": "GOLDSAM-Sync"}
        )
        total = 0
        with urllib.request.urlopen(req, timeout=300) as r, open(target, "wb") as f:
            while True:
                chunk = r.read(1024 * 256)  # 256 KB
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                # Basit progress
                sys.stdout.write(f"\r  {total/1024/1024:.1f} MB")
                sys.stdout.flush()
        print()
        return True
    except Exception as e:
        print(f"[HATA] indirme: {e}")
        if target.exists():
            try:
                target.unlink()
            except Exception:
                pass
        return False


def add_readme_to_zip(zip_path: Path) -> bool:
    """OKU_BENI.txt'yi zip'in icine ekle (eger eksikse)."""
    if not README_PATH.exists():
        return True
    try:
        # Var mi kontrol
        with zipfile.ZipFile(zip_path, "r") as z:
            names = z.namelist()
            if any(n.endswith("OKU_BENI.txt") for n in names):
                return True
        # Yoksa ekle
        with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as z:
            z.write(README_PATH, "OKU_BENI.txt")
        print("OKU_BENI.txt zip'e eklendi")
        return True
    except Exception as e:
        print(f"[UYARI] OKU_BENI ekleme: {e}")
        return True  # critical degil


def clean_old_zips(keep_name: str) -> None:
    """Eski versiyon zip'leri sil (sadece son surum kalir)."""
    for old in ROOT.glob("GOLDSAM_V2_v*.zip"):
        if old.name != keep_name:
            try:
                old.unlink()
                print(f"Silindi: {old.name}")
            except Exception:
                pass


def main() -> int:
    tag = latest_tag()
    if not tag:
        print("Latest tag okunamadi — internet veya GitHub baglanti hatasi")
        return 1

    target_name = f"GOLDSAM_V2_v{tag}.zip"
    target = ROOT / target_name

    if target.exists():
        size_mb = target.stat().st_size / 1024 / 1024
        print(f"Zaten guncel: {target_name} ({size_mb:.1f} MB)")
        clean_old_zips(target_name)
        return 0

    # Indir
    tmp = target.with_suffix(".part")
    if not download_zip(tmp):
        return 1
    tmp.rename(target)

    size_mb = target.stat().st_size / 1024 / 1024
    print(f"\nOK: {target_name} ({size_mb:.1f} MB)")

    # README ekle (varsa)
    add_readme_to_zip(target)

    # Eski sürüm zip'lerini sil
    clean_old_zips(target_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
