# -*- coding: utf-8 -*-
"""
separate.py —— 后台分离引擎（由窗口程序调用，不直接双击）

流程：调用 demucs 分离 -> 取伴奏/人声 -> 转 320k mp3 -> 保存到目标目录
进度以 "PROGRESS <0-100>" 逐行输出到 stdout，供窗口读取。
"""
import os
import re
import sys
import glob
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 模型缓存指到便携包内，避免写用户目录、也避免重复下载
os.environ.setdefault("TORCH_HOME", os.path.join(ROOT, "models"))
# 便携包里的 ffmpeg（若存在）优先用于解码 m4a 等格式
_FF = os.path.join(ROOT, "bin", "ffmpeg.exe")
if os.path.exists(_FF):
    os.environ["PATH"] = os.path.join(ROOT, "bin") + os.pathsep + os.environ.get("PATH", "")

PCT = re.compile(rb"(\d{1,3})%")


def emit(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def run_demucs(src, outdir):
    cmd = [sys.executable, "-m", "demucs",
           "-n", "htdemucs", "--two-stems=vocals", "--int24",
           "-o", outdir, src]
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, bufsize=0)
    buf = b""
    last = -1
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buf += chunk
        # tqdm 用 \r 刷新，按 \r 和 \n 切开逐段找百分比
        parts = re.split(rb"[\r\n]", buf)
        buf = parts.pop() if buf[-1:] not in (b"\r", b"\n") else b""
        for p in parts:
            m = PCT.search(p)
            if m:
                # demucs 只占 0-95，留出最后一段给转码，避免进度条倒退
                v = int(int(m.group(1)) * 0.95)
                if v != last:
                    last = v
                    emit("PROGRESS %d" % v)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("分离失败（返回码 %s）" % proc.returncode)


def to_mp3(wav_path, mp3_path):
    import soundfile as sf
    import lameenc
    data, sr = sf.read(wav_path, dtype="int16")
    ch = 1 if getattr(data, "ndim", 1) == 1 else data.shape[1]
    enc = lameenc.Encoder()
    enc.set_bit_rate(320)
    enc.set_in_sample_rate(sr)
    enc.set_channels(ch)
    enc.set_quality(2)
    blob = enc.encode(data.tobytes()) + enc.flush()
    with open(mp3_path, "wb") as f:
        f.write(blob)


def normalize(src, tmpdir):
    """用 ffmpeg 统一转成 44.1k 立体声 wav，避免各种格式的解码兼容问题。
    ffmpeg 不在时原样返回，由 demucs 自己解码。"""
    if not os.path.exists(_FF):
        return src
    out = os.path.join(tmpdir, "input.wav")
    cmd = [_FF, "-y", "-hide_banner", "-loglevel", "error",
           "-i", src, "-vn", "-ac", "2", "-ar", "44100", out]
    p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if p.returncode != 0 or not os.path.exists(out):
        return src          # 转码失败就交给原文件，不阻断流程
    return out


def main():
    if len(sys.argv) < 3:
        emit("ERROR 参数不正确")
        return 2
    src = sys.argv[1]
    outdir = sys.argv[2]
    if not os.path.exists(src):
        emit("ERROR 找不到文件：%s" % src)
        return 2
    os.makedirs(outdir, exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="sep_")
    try:
        emit("PROGRESS 1")
        feed = normalize(src, tmp)
        run_demucs(feed, tmp)

        found = {}
        for name in ("no_vocals", "vocals"):
            hits = glob.glob(os.path.join(tmp, "**", name + ".wav"), recursive=True)
            if hits:
                found[name] = hits[0]
        if "no_vocals" not in found:
            emit("ERROR 没有生成伴奏文件")
            return 3

        stem = os.path.splitext(os.path.basename(src))[0]
        emit("PROGRESS 96")
        jobs = [("no_vocals", "伴奏"), ("vocals", "人声")]
        saved = []
        for key, label in jobs:
            if key not in found:
                continue
            out_mp3 = os.path.join(outdir, "%s-%s.mp3" % (stem, label))
            to_mp3(found[key], out_mp3)
            saved.append(out_mp3)
        emit("PROGRESS 100")
        emit("DONE " + outdir)
        return 0
    except Exception as e:
        emit("ERROR %s" % e)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
