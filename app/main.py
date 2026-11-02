# -*- coding: utf-8 -*-
"""
一键伴奏 · 窗口程序
拖入歌曲 -> 选好输出位置 -> 点「开始分离」-> 得到「伴奏」和「人声」
"""
import os
import sys
import json
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except Exception:
    HAS_DND = False

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, "python", "python.exe")
ENGINE = os.path.join(HERE, "separate.py")
ICON = os.path.join(HERE, "icon.ico")
CONF = os.path.join(HERE, "settings.json")
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
DEFAULT_OUT = os.path.join(DESKTOP, "伴奏输出")
AUDIO_EXT = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma")

BG = "#F4F4F8"
CARD = "#FFFFFF"
ACCENT = "#7F77DD"
ACCENT_D = "#645CC7"
INK = "#2C2C32"
MUTED = "#9A9AA6"
LINE = "#E4E2F2"
GREY_BG = "#ECEBF3"
GREY_D = "#E2E0EC"

FONT = ("Microsoft YaHei UI", 10)
FONT_B = ("Microsoft YaHei UI", 10, "bold")
FONT_T = ("Microsoft YaHei UI", 20, "bold")
FONT_S = ("Microsoft YaHei UI", 9)
FONT_XS = ("Microsoft YaHei UI", 8)


# ---------- 配置文件 ----------
def load_conf():
    try:
        with open(CONF, "r", encoding="utf-8") as f:
            p = (json.load(f) or {}).get("output_dir")
        if p:
            parent = os.path.dirname(os.path.normpath(p))
            if os.path.isdir(parent):
                return os.path.normpath(p)
    except Exception:
        pass
    return DEFAULT_OUT


def save_conf(out):
    try:
        with open(CONF, "w", encoding="utf-8") as f:
            json.dump({"output_dir": out}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def short_path(p, limit=36):
    if len(p) <= limit:
        return p
    keep = limit - 3
    head = keep // 2
    tail = keep - head
    return p[:head] + "..." + p[-tail:]


# ---------- 圆角按钮 ----------
class RoundButton(tk.Canvas):
    """Canvas 画的圆角按钮（原生 Button 只能是方角）"""

    def __init__(self, master, text, command, width=214, height=46, radius=12):
        tk.Canvas.__init__(self, master, width=width, height=height,
                           highlightthickness=0, bd=0, bg=BG, cursor="arrow")
        self._cw, self._chh = width, height
        self._cmd = command
        self._on = False
        self._hover = False
        self._shape = self._round(1, 1, width - 1, height - 1, radius)
        self._label = self.create_text(width / 2, height / 2, text=text,
                                       font=FONT_B, fill="#A9A7BC")
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._paint()

    def _round(self, x1, y1, x2, y2, r):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
               x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
               x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(pts, smooth=True, outline="", fill=GREY_BG)

    def _paint(self):
        if not self._on:
            fill, fg = GREY_BG, "#A9A7BC"
        elif self._hover:
            fill, fg = ACCENT_D, "#FFFFFF"
        else:
            fill, fg = ACCENT, "#FFFFFF"
        self.itemconfigure(self._shape, fill=fill)
        self.itemconfigure(self._label, fill=fg)
        self.configure(cursor="hand2" if self._on else "arrow")

    def set_enabled(self, on):
        self._on = bool(on)
        self._hover = False
        self._paint()

    def set_text(self, text):
        self.itemconfigure(self._label, text=text)

    def _click(self, _e):
        if self._on and self._cmd:
            self._cmd()

    def _enter(self, _e):
        if self._on:
            self._hover = True
            self._paint()

    def _leave(self, _e):
        if self._hover:
            self._hover = False
            self._paint()


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.pending = None      # 已选好、等着分离的文件
        self.after_done = False  # 上一首已完成
        self.outdir = load_conf()

        root.title("一键伴奏 · 人声分离")
        root.resizable(False, False)
        root.configure(bg=BG)
        if os.path.exists(ICON):
            try:
                root.iconbitmap(ICON)
            except Exception:
                pass

        # 标题
        tk.Label(root, text="一键伴奏", font=FONT_T, bg=BG, fg=INK).pack(pady=(24, 2))
        tk.Label(root, text="拖一首歌进来，自动分出伴奏和人声", font=FONT_S,
                 bg=BG, fg=MUTED).pack()

        # 拖放区
        self.drop = tk.Frame(root, bg=CARD, highlightthickness=1,
                             highlightbackground=LINE, height=148)
        self.drop.pack(fill="x", padx=34, pady=(18, 12))
        self.drop.pack_propagate(False)

        self.d_icon = tk.Label(self.drop, text="♪", font=("Microsoft YaHei UI", 28),
                               bg=CARD, fg=ACCENT)
        self.d_icon.pack(pady=(24, 2))
        self.d_title = tk.Label(self.drop, text="把歌曲拖到这里", font=FONT_B, bg=CARD, fg=INK)
        self.d_title.pack()
        self.d_sub = tk.Label(self.drop, text="或者点这里选择文件 · mp3 / wav / flac / m4a",
                              font=FONT_S, bg=CARD, fg=MUTED)
        self.d_sub.pack(pady=(4, 0))
        for w in (self.drop, self.d_icon, self.d_title, self.d_sub):
            w.bind("<Button-1>", lambda e: self.pick())

        # 输出目录
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=34, pady=(0, 14))
        self.btn_open = tk.Button(row, text="打开", font=FONT_XS, relief="flat",
                                  bg=GREY_BG, fg="#5F5F6B", activebackground=GREY_D,
                                  cursor="hand2", padx=8, pady=2, bd=0,
                                  command=self.open_dir)
        self.btn_open.pack(side="right")
        self.btn_chg = tk.Button(row, text="更改", font=FONT_XS, relief="flat",
                                 bg=GREY_BG, fg="#5F5F6B", activebackground=GREY_D,
                                 cursor="hand2", padx=8, pady=2, bd=0,
                                 command=self.choose_dir)
        self.btn_chg.pack(side="right", padx=(0, 6))
        tk.Label(row, text="输出到", font=FONT_XS, bg=BG, fg=MUTED).pack(side="left")
        self.out_lbl = tk.Label(row, text=short_path(self.outdir), font=FONT_XS,
                                bg=BG, fg="#6B6B78", anchor="w")
        self.out_lbl.pack(side="left", padx=(6, 8), fill="x", expand=True)

        # 进度
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Bar.Horizontal.TProgressbar", troughcolor="#E6E4F0",
                        background=ACCENT, bordercolor="#E6E4F0",
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        self.bar = ttk.Progressbar(root, style="Bar.Horizontal.TProgressbar",
                                   maximum=100, length=424)
        self.bar.pack(fill="x", padx=34, pady=(10, 8))
        self.status = tk.Label(root, text="准备就绪", font=FONT_S, bg=BG, fg=MUTED)
        self.status.pack()

        # 主按钮
        self.btn = RoundButton(root, "开始分离", self.on_start)
        self.btn.pack(pady=(16, 14))

        tk.Label(root, text="全程在本机处理，文件不会上传", font=FONT_XS,
                 bg=BG, fg="#B9B9C4").pack(pady=(0, 16))

        if HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)
            self.drop.dnd_bind("<<DropEnter>>", lambda e: self.hl(True))
            self.drop.dnd_bind("<<DropLeave>>", lambda e: self.hl(False))

        self.root.after(120, self.poll)

    # ---------- 交互 ----------
    def hl(self, on):
        if self.busy:
            return
        self.drop.configure(highlightbackground=ACCENT if on else LINE,
                            highlightthickness=2 if on else 1)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        self.hl(False)
        if files and not self.busy:
            self.set_file(files[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(
            title="选择要分离的歌曲",
            filetypes=[("音频文件", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.wma"),
                       ("所有文件", "*.*")])
        if p:
            self.set_file(p)

    def set_file(self, path):
        """选好文件，但不自动开始，等用户点按钮"""
        if self.busy:
            return
        if not path.lower().endswith(AUDIO_EXT):
            if not messagebox.askyesno("确认", "这个文件看起来不是音频，仍然尝试？"):
                return
        self.pending = path
        self.after_done = False
        name = os.path.basename(path)
        if len(name) > 30:
            name = name[:14] + "..." + name[-13:]
        self.d_icon.configure(text="♪")
        self.d_title.configure(text=name)
        self.d_sub.configure(text="已选好，点下面的「开始分离」")
        self.status.configure(text="等待开始", fg=MUTED)
        self.bar["value"] = 0
        self.btn.set_text("开始分离")
        self.btn.set_enabled(True)

    def reset_drop(self):
        self.d_icon.configure(text="♪")
        self.d_title.configure(text="把歌曲拖到这里")
        self.d_sub.configure(text="或者点这里选择文件 · mp3 / wav / flac / m4a")

    def choose_dir(self):
        if self.busy:
            return
        p = filedialog.askdirectory(title="选择伴奏保存的位置",
                                    initialdir=self.outdir)
        if not p:
            return
        self.outdir = os.path.normpath(p)
        save_conf(self.outdir)
        self.out_lbl.configure(text=short_path(self.outdir))
        self.status.configure(text="输出位置已改为 %s" % os.path.basename(self.outdir), fg=MUTED)

    def open_dir(self):
        try:
            os.makedirs(self.outdir, exist_ok=True)
            os.startfile(self.outdir)
        except Exception:
            messagebox.showinfo("输出目录", self.outdir)

    # ---------- 处理 ----------
    def on_start(self):
        if self.busy:
            return
        if self.after_done:      # 上一首处理完了，这个按钮变成「再处理一首」
            self.after_done = False
            self.pending = None
            self.reset_drop()
            self.status.configure(text="准备就绪", fg=MUTED)
            self.bar["value"] = 0
            self.btn.set_text("开始分离")
            self.btn.set_enabled(False)
            self.pick()
            return
        if not self.pending:
            self.pick()
            return
        self.start(self.pending)

    def start(self, path):
        if self.busy:
            return
        if not os.path.exists(PY):
            messagebox.showerror("缺少组件", "找不到 python 运行环境，请把整个文件夹解压后再运行。")
            return
        try:
            os.makedirs(self.outdir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("输出目录不可用", "无法创建目录：\n%s\n\n%s" % (self.outdir, e))
            return

        self.busy = True
        self.after_done = False
        self.bar["value"] = 0
        self.status.configure(text="正在读取：%s" % os.path.basename(path), fg=MUTED)
        self.d_title.configure(text="处理中，请不要关闭窗口")
        self.d_sub.configure(text=os.path.basename(path)[:30])
        self.btn.set_text("分离中…")
        self.btn.set_enabled(False)

        t = threading.Thread(target=self.worker, args=(path, self.outdir), daemon=True)
        t.start()

    def worker(self, path, outdir):
        cmd = [PY, ENGINE, path, outdir]
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    cwd=ROOT, creationflags=flags, bufsize=0)
        except Exception as e:
            self.q.put(("error", "无法启动处理程序：%s" % e))
            return
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("PROGRESS"):
                try:
                    self.q.put(("p", int(line.split()[1])))
                except Exception:
                    pass
            elif line.startswith("DONE"):
                self.q.put(("done", outdir))
            elif line.startswith("ERROR"):
                self.q.put(("error", line[6:].strip()))
        proc.wait()

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "p":
                    self.bar["value"] = val
                    self.status.configure(text=self.stage_text(val), fg=MUTED)
                elif kind == "done":
                    self.finish(True, val)
                elif kind == "error":
                    self.finish(False, val)
        except queue.Empty:
            pass
        self.root.after(120, self.poll)

    @staticmethod
    def stage_text(v):
        if v < 2:
            return "正在分析音频…"
        if v < 95:
            return "正在分离人声（%d%%）· 一首歌大约 2-5 分钟" % v
        return "正在生成 mp3…"

    def finish(self, ok, info):
        self.busy = False
        if ok:
            self.bar["value"] = 100
            self.status.configure(text="完成！已保存到 %s" % info, fg="#2E9E6B")
            self.d_title.configure(text="分离完成")
            self.d_sub.configure(text="伴奏和人声已保存，点下方按钮处理下一首")
            self.btn.set_text("再处理一首")
            self.btn.set_enabled(True)
            self.after_done = True
            try:
                os.startfile(info)
            except Exception:
                pass
        else:
            self.status.configure(text="出错了", fg="#C0504D")
            self.d_title.configure(text="处理失败")
            self.d_sub.configure(text=str(info)[:40])
            self.btn.set_text("重试")
            self.btn.set_enabled(True)
            messagebox.showerror("处理失败", str(info))


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as _e:
        import traceback
        log = os.path.join(HERE, "error.log")
        try:
            with open(log, "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
        except Exception:
            pass
        try:
            import tkinter.messagebox as mb
            mb.showerror("启动失败", "程序启动出错：\n%s\n\n详细日志：%s" % (_e, log))
        except Exception:
            pass
