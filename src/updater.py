"""Проверка и загрузка обновлений PTW из релизов GitHub.

Релиз на GitHub: тег вида v1.2.0, в нём файл-установщик PTW-Setup-1.2.0.exe.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import urllib.request

from version import GITHUB_REPO, __version__

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
HEADERS = {"User-Agent": f"PTW/{__version__}", "Accept": "application/vnd.github+json"}


class UpdateInfo:
    def __init__(self, version, notes, url, size, sha256):
        self.version = version
        self.notes = notes
        self.url = url
        self.size = size
        self.sha256 = sha256


def parse_version(text):
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def is_configured():
    return not GITHUB_REPO.startswith("OWNER/")


def check():
    """Вернуть UpdateInfo, если на GitHub есть версия новее текущей, иначе None."""
    if not is_configured():
        return None
    req = urllib.request.Request(API_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        release = json.load(resp)
    latest = release.get("tag_name", "").lstrip("vV")
    if parse_version(latest) <= parse_version(__version__):
        return None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.startswith("PTW-Setup") and name.lower().endswith(".exe"):
            digest = asset.get("digest") or ""
            sha256 = digest.split(":", 1)[1] if digest.startswith("sha256:") else None
            return UpdateInfo(latest, release.get("body") or "", asset["browser_download_url"],
                              asset.get("size"), sha256)
    return None


def download(info, on_progress):
    """Скачать установщик во временную папку, проверить размер и хеш. Возвращает путь."""
    path = os.path.join(tempfile.gettempdir(), f"PTW-Setup-{info.version}.exe")
    req = urllib.request.Request(info.url, headers={"User-Agent": HEADERS["User-Agent"]})
    h = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp, open(path, "wb") as f:
        total = info.size or int(resp.headers.get("Content-Length") or 0)
        while chunk := resp.read(256 * 1024):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if total:
                on_progress(done / total)
    if info.size and done != info.size:
        raise IOError("файл скачался не полностью")
    if info.sha256 and h.hexdigest().lower() != info.sha256.lower():
        raise IOError("контрольная сумма не совпала")
    return path


def run_installer(path):
    """Запустить установщик в тихом режиме; после установки он сам перезапустит PTW."""
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                     close_fds=True)
