# 一键伴奏 · banzou

把一个按钮都不用点的 **人声 / 伴奏分离** 工具，做成 Windows 上双击就能用的绿色包。

拖一首歌进窗口，几分钟后桌面上就会出现两个文件：**伴奏** 和 **人声（清唱）**。

> 核心场景：想唱一首歌但找不到伴奏；想把一段采访的人声单独留下；想给视频配乐但原曲有人唱。
> 现成的在线工具要么收费、要么上传、要么给你加个水印。这个不需要联网，也不上传任何东西。

---

## 特性

| | |
|---|---|
| **拖拽即用** | 把歌拖进窗口就开始，没有参数、没有命令行 |
| **完全离线** | 模型和运行环境都打包在本地，处理全程不联网 |
| **免安装** | 不写注册表、不装服务、不常驻后台，删文件夹即卸载 |
| **8 种输入格式** | mp3 / wav / flac / m4a / aac / ogg / wma / 手机录音 |
| **双轨输出** | 伴奏和人声各一份，320kbps MP3，44.1kHz 立体声 |
| **开源** | 代码 MIT，引擎是 Meta 的 Demucs |

## 效果说明

- **录音室版本**：分离得很干净，伴奏基本听不到人声
- **现场版 / 混响重的版本**：伴奏里会残留一点人声「影子」，尤其在副歌人声密集处。这是分离技术的物理上限，任何工具都做不到 100%
- 分离出的 **人声轨** 也有用：清唱、合唱版、二创素材

## 速度

纯 CPU 推理，一首 3~4 分钟的歌：

- 轻薄本（i5 / R5）：约 3~5 分钟
- 台式机 / 标压处理器：约 2~3 分钟

不需要独立显卡（显存小于 4GB 的机器跑 GPU 反而会失败）。

---

## 怎么拿到能用的版本

仓库里只有源码。成品约 **300MB**（完整的 Python 运行时 + PyTorch + 80MB 模型），超出代码仓库的合理体积，所以不放进来。

想要双击就能跑的版本，用下一节的「自己构建」——一条命令，约 10 分钟，时间基本都花在下载依赖上。

构建完成后会得到 `一键伴奏-便携版.zip`，解压后双击 `一键伴奏.bat`，结果保存在 `桌面\伴奏输出\`。

详细说明见包内的 `使用说明.txt`。

---

## 自己构建

> 下面这套流程在 Windows 10/11 + Python 3.10+ 上验证过。

### 一键构建

```bash
python build/build_portable.py
```

脚本会依次完成：下载便携 Python → 安装依赖 → 下载模型 → 下载 ffmpeg → 组装目录 → 打包 zip。
已存在的文件会自动跳过，中断后可以重跑。

### 手动构建（脚本失败时的备选）

```bash
# 1. 下载便携 Python（含 tkinter，解压即用、可任意换路径）
#    https://github.com/astral-sh/python-build-standalone/releases
#    取 cpython-3.13.x-x86_64-pc-windows-msvc-install_only_stripped.tar.gz
#    解压后把 python/ 放到项目根目录

# 2. 安装依赖（用便携 Python 自带的 pip，或先建一个 venv）
python/python.exe -m pip install -r build/requirements.txt

# 3. 下载模型（80MB）到 models/hub/checkpoints/
#    https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th

# 4. 下载 ffmpeg 放到 bin/ffmpeg.exe
#    https://www.gyan.dev/ffmpeg/builds/  取 essentials 版即可

# 5. 打包
#    把 app/、一键伴奏.bat、使用说明.txt、python/、models/、bin/ 放在同一个文件夹里
#    压缩成 zip 就是成品
```

### 目录结构（构建完成后）

```
一键伴奏/
├─ 一键伴奏.bat           启动器
├─ 使用说明.txt            给最终用户看的说明
├─ app/
│  ├─ main.py             窗口界面（tkinter）
│  └─ separate.py         分离引擎（调 demucs + 转 mp3）
├─ python/                便携 Python 运行时（构建时生成）
├─ models/hub/checkpoints/
│  └─ 955717e8-8726e21a.th   htdemucs 模型（构建时生成）
└─ bin/
   └─ ffmpeg.exe          格式解码（构建时生成）
```

仓库里只提交源码，`python/`、`models/`、`bin/`、`*.zip` 都在 `.gitignore` 里。

---

## 工作原理

```
拖入文件
   ↓
ffmpeg 统一转成 44.1kHz 双声道 wav（吃掉所有格式差异）
   ↓
demucs（htdemucs 模型）分离成 vocals / no_vocals 两轨
   ↓
lameenc 编码成 320kbps mp3
   ↓
保存到 桌面\伴奏输出\
```

界面与引擎是**两个进程**：窗口只负责画界面和读进度，真正的计算在 `separate.py` 子进程里跑。
这样界面永远不会因为加载模型而卡住，处理过程中也能看到实时百分比。

进度协议很简单，引擎往 stdout 打三行：

```
PROGRESS 42
DONE <输出目录>
ERROR <错误信息>
```

---

## 常见问题

**杀毒软件报警？**
PyTorch 的 dll 体积大，容易被启发式规则误判。程序不联网、不写注册表、不常驻后台。可以断网使用验证，或把文件夹加白名单。

**第一次打开慢？**
要加载 80MB 模型，等 2~3 秒。

**为什么不做成单文件 exe？**
PyInstaller 打包 torch 后体积会到 1GB 以上，而且每次启动要先解压到临时目录，20~30 秒才能出界面，还更容易被杀软拦。绿色文件夹反而是体验最好的形态。

**能不能分离更多轨？**
可以。把 `separate.py` 里的 `--two-stems=vocals` 去掉，demucs 会输出 drums / bass / other / vocals 四条轨。

**支持 Mac / Linux 吗？**
代码是跨平台的（tkinter + demucs），但目前的构建脚本只处理 Windows。Mac 上装上 Python 和依赖，直接 `python app/main.py` 也能跑。

---

## 许可与致谢

- 本项目代码：MIT
- 分离引擎：[Demucs](https://github.com/facebookresearch/demucs)（Meta Research，MIT）
- 模型权重：htdemucs，版权归 Meta 所有，随 Demucs 发布
- 便携运行时：[python-build-standalone](https://github.com/astral-sh/python-build-standalone)
- 音视频处理：[FFmpeg](https://ffmpeg.org/)（GPL）

**版权提醒**：本工具仅供个人学习、练唱伴奏、私下翻唱等合法用途。分离他人音乐作品产生的衍生文件，请勿用于商业发行或侵犯著作权的场景。音乐版权归原作者及唱片公司所有。
