# -*- coding: utf-8 -*-
"""
separate.py —— 后台分离引擎（由窗口程序调用，不直接双击）

流程：调用 demucs 分离 -> 取伴奏/人声 -> 转 320k mp3 -> 保存到目标目录
进度以 "PROGRESS <0-100>" 逐行输出到 stdout，供窗口读取。
出错时把完整诊断写入 app/error.log，供回传排查。
"""
import os
import re
import sys
import glob
import shutil
import tempfile
import platform
import datetime
import traceback
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOG = os.path.join(HERE, "error.log")

# 模型缓存指到便携包内，避免写用户目录、也避免重复下载
os.environ.setdefault("TORCH_HOME", os.path.join(ROOT, "models"))
# 便携包里的 ffmpeg（若存在）优先用于解码 m4a 等格式
_FF = os.path.join(ROOT, "bin", "ffmpeg.exe")
if os.path.exists(_FF):
    os.environ["PATH"] = os.path.join(ROOT, "bin") + os.pathsep + os.environ.get("PATH", "")

PCT = re.compile(rb"(\d{1,3})%")


# ---------- 输出编码 ----------
def force_utf8():
    """Windows 中文版把管道 stdout 设成 GBK，会让中文报错在主窗口变菱形问号。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def emit(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def dec(b):
    """子进程输出可能是 UTF-8（Python 层）或 GBK（C++/系统层），逐个试。"""
    if isinstance(b, str):
        return b
    for enc in ("utf-8", "gbk", "mbcs"):
        try:
            return b.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return b.decode("utf-8", "replace")


# ---------- 诊断日志 ----------
def reset_log(src, outdir):
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("一键伴奏 · 诊断日志\n")
            f.write("时间   ：%s\n" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            f.write("系统   ：%s\n" % platform.platform())
            f.write("架构   ：%s\n" % platform.machine())
            f.write("Python ：%s\n" % sys.version.split()[0])
            f.write("输入   ：%s\n" % src)
            try:
                f.write("大小   ：%.1f KB\n" % (os.path.getsize(src) / 1024.0))
            except Exception:
                pass
            f.write("输出   ：%s\n" % outdir)
            f.write("ffmpeg ：%s\n" % ("有" if os.path.exists(_FF) else "无"))
            model = os.path.join(os.environ.get("TORCH_HOME", ""), "hub",
                                 "checkpoints", "955717e8-8726e21a.th")
            f.write("模型   ：%s（%s）\n" % (model, "存在" if os.path.exists(model) else "缺失"))
            f.write("=" * 50 + "\n")
    except Exception:
        pass


def log(title, detail=""):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("\n--- %s ---\n" % title)
            if detail:
                f.write(str(detail).rstrip() + "\n")
    except Exception:
        pass


# ---------- 各步骤 ----------
def run_demucs(src, outdir):
    cmd = [sys.executable, "-m", "demucs",
           "-n", "htdemucs", "--two-stems=vocals", "--int24",
           "-o", outdir, src]
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, bufsize=0)
    buf = b""
    last = -1
    tail = []          # 保留最后若干行原始输出，失败时写进日志
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
            else:
                txt = dec(p).strip()
                if txt and len(txt) < 600:
                    tail.append(txt)
                    if len(tail) > 60:
                        tail.pop(0)
    proc.wait()
    if buf:
        txt = dec(buf).strip()
        if txt and len(txt) < 600:
            tail.append(txt)
    log("demucs 原始输出（最后 20 行）", "\n".join(tail[-20:]))
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
        # 记录失败原因，但不阻断流程：交给 demucs 自己解码试试
        log("ffmpeg 解码失败，改由 demucs 直接读原文件", dec(p.stderr)[:2000])
        return src
    return out


def main():
    force_utf8()
    if len(sys.argv) < 3:
        emit("ERROR 参数不正确")
        return 2
    src = sys.argv[1]
    outdir = sys.argv[2]
    reset_log(src, outdir)

    if not os.path.exists(src):
        emit("ERROR 找不到文件：%s" % src)
        return 2

    model = os.path.join(os.environ.get("TORCH_HOME", ""), "hub",
                         "checkpoints", "955717e8-8726e21a.th")
    if not os.path.exists(model):
        log("模型文件缺失", "离线状态下无法自动下载。请确认 models\\hub\\checkpoints\\ 里有 955717e8-8726e21a.th")
        emit("ERROR 找不到分离模型，请检查 models 文件夹是否完整")
        return 4

    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        log("输出目录不可写", traceback.format_exc())
        emit("ERROR 无法创建输出目录：%s" % e)
        return 5

    tmp = tempfile.mkdtemp(prefix="sep_")
    log("临时目录", tmp)
    try:
        emit("PROGRESS 1")
        feed = normalize(src, tmp)
        log("送入 demucs 的文件", feed)
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
        for key, label in jobs:
            if key not in found:
                continue
            out_mp3 = os.path.join(outdir, "%s-%s.mp3" % (stem, label))
            to_mp3(found[key], out_mp3)
            log("已生成", out_mp3)
        emit("PROGRESS 100")
        emit("DONE " + outdir)
        return 0
    except Exception as e:
        log("失败原因：%s" % e, traceback.format_exc())
        # 协议只认单行，去掉换行，详情留在日志里
        emit("ERROR %s" % str(e).replace("\r", " ").replace("\n", " | "))
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
