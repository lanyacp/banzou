# -*- coding: utf-8 -*-
"""
build_portable.py —— 构建 Windows 便携包

用法（在项目根目录）：
    python build/build_portable.py

流程：
    1. 下载免安装 Python（含 tkinter）
    2. 安装依赖
    3. 下载 htdemucs 模型
    4. 下载 ffmpeg
    5. 组装目录
    6. 打包 zip

已存在的文件会自动跳过，中断后可直接重跑。
"""
import io
import os
import sys
import json
import shutil
import tarfile
import zipfile
import urllib.request
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "一键伴奏")
PYDIR = os.path.join(PKG, "python")
MODELDIR = os.path.join(PKG, "models", "hub", "checkpoints")
BINDIR = os.path.join(PKG, "bin")

# 国内加速前缀；网络直连正常的话把它改成 ""
PROXY = os.environ.get("BUILD_PROXY", "https://gh-proxy.com/")

PBS_API = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
MODEL_URL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
FFMPEG_URL = ("https://github.com/GyanD/codexffmpeg/releases/download/8.1/"
              "ffmpeg-8.1-essentials_build.zip")
PYPI = "https://pypi.tuna.tsinghua.edu.cn/simple"


def log(msg):
    print("\n▶ " + msg, flush=True)


def fetch(url, dest, desc=""):
    """下载到 dest，已存在则跳过。"""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print("  已存在，跳过：%s" % os.path.basename(dest))
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    real = url if url.startswith("http") and "gitee" in url else PROXY + url
    print("  下载 %s" % (desc or os.path.basename(dest)))
    tmp = dest + ".part"
    with urllib.request.urlopen(real, timeout=180) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                sys.stdout.write("\r    %3d%%  %.1f/%.1f MB" %
                                 (pct, done / 1048576, total / 1048576))
                sys.stdout.flush()
    print()
    os.replace(tmp, dest)
    return dest


def step_python():
    log("1/6 准备便携 Python")
    if os.path.exists(os.path.join(PYDIR, "python.exe")):
        print("  已存在，跳过")
        return
    with urllib.request.urlopen(PROXY + PBS_API, timeout=60) as r:
        rel = json.load(r)
    asset = next(a for a in rel["assets"]
                 if "x86_64-pc-windows-msvc-install_only_stripped.tar.gz" in a["name"]
                 and a["name"].startswith("cpython-3.13"))
    print("  使用 %s" % asset["name"])
    tmp = os.path.join(ROOT, "build", "tmp")
    os.makedirs(tmp, exist_ok=True)
    pkg = fetch(asset["browser_download_url"], os.path.join(tmp, "python.tar.gz"), "便携 Python")
    with tarfile.open(pkg, "r:gz") as t:
        t.extractall(tmp)
    shutil.move(os.path.join(tmp, "python"), PYDIR)
    print("  Python 就位：%s" % PYDIR)


def step_deps():
    log("2/6 安装依赖（约 700MB，第一次会比较久）")
    py = os.path.join(PYDIR, "python.exe")
    req = os.path.join(ROOT, "build", "requirements.txt")
    subprocess.check_call([py, "-m", "pip", "install", "--no-warn-script-location",
                           "-r", req, "-i", PYPI, "-q"])
    print("  依赖安装完成")


def step_model():
    log("3/6 下载 htdemucs 模型（80MB）")
    fetch(MODEL_URL, os.path.join(MODELDIR, "955717e8-8726e21a.th"), "htdemucs 模型")


def step_ffmpeg():
    log("4/6 下载 ffmpeg")
    dest = os.path.join(BINDIR, "ffmpeg.exe")
    if os.path.exists(dest):
        print("  已存在，跳过")
        return
    tmp = os.path.join(ROOT, "build", "tmp", "ffmpeg.zip")
    fetch(FFMPEG_URL, tmp, "ffmpeg essentials")
    with zipfile.ZipFile(tmp) as z:
        name = next(n for n in z.namelist() if n.endswith("bin/ffmpeg.exe"))
        os.makedirs(BINDIR, exist_ok=True)
        with z.open(name) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
    print("  ffmpeg 就位：%s" % dest)


def step_assemble():
    log("5/6 组装程序文件")
    os.makedirs(os.path.join(PKG, "app"), exist_ok=True)
    for f in ("main.py", "separate.py", "icon.ico"):
        shutil.copy2(os.path.join(ROOT, "app", f), os.path.join(PKG, "app", f))
    for f in ("一键伴奏.bat", "使用说明.txt"):
        shutil.copy2(os.path.join(ROOT, f), os.path.join(PKG, f))
    print("  程序文件已复制")


def step_pack():
    log("6/6 打包 zip")
    out = os.path.join(ROOT, "一键伴奏-便携版")
    if os.path.exists(out + ".zip"):
        os.remove(out + ".zip")
    shutil.make_archive(out, "zip", ROOT, "一键伴奏")
    size = os.path.getsize(out + ".zip") / 1048576
    print("  完成：%s.zip  （%.0f MB）" % (out, size))


def main():
    os.makedirs(PKG, exist_ok=True)
    step_python()
    step_deps()
    step_model()
    step_ffmpeg()
    step_assemble()
    step_pack()
    shutil.rmtree(os.path.join(ROOT, "build", "tmp"), ignore_errors=True)
    print("\n全部完成。发给别人的就是 一键伴奏-便携版.zip")


if __name__ == "__main__":
    main()
