# -*- coding: utf-8 -*-
"""
一键伴奏 · 窗口程序
把歌曲拖进窗口 -> 自动分出「伴奏」和「人声」-> 存到桌面\伴奏输出
"""
import os
import sys
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
DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
OUTDIR = os.path.join(DESKTOP, "伴奏输出")

BG = "#F4F4F8"
CARD = "#FFFFFF"
ACCENT = "#7F77DD"
ACCENT_D = "#645CC7"
INK = "#2C2C32"
MUTED = "#9A9AA6"
LINE = "#E4E2F2"

FONT = ("Microsoft YaHei UI", 10)
FONT_B = ("Microsoft YaHei UI", 10, "bold")
FONT_T = ("Microsoft YaHei UI", 20, "bold")
FONT_S = ("Microsoft YaHei UI", 9)


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.outdir = OUTDIR

        root.title("一键伴奏 · 人声分离")
        root.geometry("560x430")
        root.resizable(False, False)
        root.configure(bg=BG)
        try:
            root.iconbitmap(default="")
        except Exception:
            pass

        # 标题
        tk.Label(root, text="一键伴奏", font=FONT_T, bg=BG, fg=INK).pack(pady=(26, 2))
        tk.Label(root, text="拖一首歌进来，自动分出伴奏和人声", font=FONT_S, bg=BG, fg=MUTED).pack()

        # 拖放区
        self.drop = tk.Frame(root, bg=CARD, highlightthickness=1,
                             highlightbackground=LINE, height=150)
        self.drop.pack(fill="x", padx=34, pady=20)
        self.drop.pack_propagate(False)
        self.drop.bind("<Button-1>", lambda e: self.pick())

        self.d_icon = tk.Label(self.drop, text="♪", font=("Microsoft YaHei UI", 30),
                               bg=CARD, fg=ACCENT)
        self.d_icon.pack(pady=(26, 4))
        self.d_title = tk.Label(self.drop, text="把歌曲拖到这里", font=FONT_B, bg=CARD, fg=INK)
        self.d_title.pack()
        self.d_sub = tk.Label(self.drop, text="或者点这里选择文件 · mp3 / wav / flac / m4a",
                              font=FONT_S, bg=CARD, fg=MUTED)
        self.d_sub.pack(pady=(4, 0))
        for w in (self.drop, self.d_icon, self.d_title, self.d_sub):
            w.bind("<Button-1>", lambda e: self.pick())

        # 进度
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Bar.Horizontal.TProgressbar", troughcolor="#ECEBF3",
                        background=ACCENT, bordercolor="#ECEBF3",
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        self.bar = ttk.Progressbar(root, style="Bar.Horizontal.TProgressbar",
                                   maximum=100, length=492)
        self.bar.pack(pady=(0, 10))
        self.status = tk.Label(root, text="准备就绪", font=FONT_S, bg=BG, fg=MUTED)
        self.status.pack()

        # 底部按钮
        btns = tk.Frame(root, bg=BG)
        btns.pack(side="bottom", pady=22)
        self.open_btn = tk.Button(btns, text="打开输出文件夹", font=FONT_S,
                                  command=self.open_dir, relief="flat",
                                  bg="#ECEBF3", fg=MUTED, activebackground="#E2E0EC",
                                  cursor="hand2", padx=16, pady=5, state="disabled")
        self.open_btn.pack()

        tk.Label(root, text="全程在本机处理，文件不会上传", font=("Microsoft YaHei UI", 8),
                 bg=BG, fg="#B9B9C4").pack(side="bottom")

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
        if files:
            self.start(files[0])

    def pick(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(
            title="选择要分离的歌曲",
            filetypes=[("音频文件", "*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.wma"),
                       ("所有文件", "*.*")])
        if p:
            self.start(p)

    def open_dir(self):
        try:
            os.startfile(self.outdir)
        except Exception:
            messagebox.showinfo("提示", "输出目录：\n" + self.outdir)

    # ---------- 处理 ----------
    def start(self, path):
        if self.busy:
            return
        if not os.path.exists(PY):
            messagebox.showerror("缺少组件", "找不到 python 运行环境，请把整个文件夹解压后再运行。")
            return
        if not path.lower().endswith((".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma")):
            if not messagebox.askyesno("确认", "这个文件看起来不是音频，仍然尝试？"):
                return

        self.busy = True
        self.bar["value"] = 0
        self.status.configure(text="正在读取：%s" % os.path.basename(path), fg=MUTED)
        self.d_title.configure(text="处理中，请不要关闭窗口")
        self.d_sub.configure(text=os.path.basename(path)[:40])
        self.open_btn.configure(state="disabled", bg="#ECEBF3", fg=MUTED)

        t = threading.Thread(target=self.worker, args=(path,), daemon=True)
        t.start()

    def worker(self, path):
        cmd = [PY, ENGINE, path, OUTDIR]
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
                self.q.put(("done", OUTDIR))
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
        self.d_title.configure(text="把歌曲拖到这里")
        self.d_sub.configure(text="或者点这里选择文件 · mp3 / wav / flac / m4a")
        if ok:
            self.bar["value"] = 100
            self.status.configure(text="完成！已保存到 桌面 \\ 伴奏输出", fg="#2E9E6B")
            self.open_btn.configure(state="normal", bg=ACCENT, fg="white",
                                    activebackground=ACCENT_D)
        else:
            self.status.configure(text="出错了", fg="#C0504D")
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
