# 第三方组件声明

本项目（GoDojo）自身代码以 MIT 许可发布，但**棋力完全来自第三方开源项目 KataGo**。
Releases 中提供的安装包内置了 KataGo 的可执行文件与官方神经网络权重，特此声明。

---

## KataGo

- **项目主页**：https://github.com/lightvector/KataGo
- **作者**：David J Wu（lightvector）
- **许可**：MIT License
- **本项目使用的部分**：
  - `katago.exe`（OpenCL 版，GPU 推理）
  - `katago.exe`（Eigen 版，CPU 推理，备用）
  - 随附的 `.dll` 运行库（libcrypto / libssl / bz2 等）
  - 默认 GTP 配置文件（本项目在其基础上调整了 `maxTime`、`numSearchThreads` 等参数）

```
MIT License

Copyright (c) 2019-2026 David J Wu ("lightvector")

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## KataGo 神经网络权重

- **来源**：KataGo Distributed Training（https://katagotraining.org/）
- **本项目使用**：`kata1-tf3-b11c768-s11500M-d6163M.bin.gz`（kata1 训练系列）

权重采用 **KataGo Neural Network License**，该许可与 MIT 等效，允许自由使用、复制、修改、合并、发布、分发、再许可和/或销售，
条件是保留版权声明与本许可声明。详见：
<https://katagotraining.org/network_license>

```
KataGo Neural Network License

Copyright 2026 David J Wu ("lightvector").

Permission is hereby granted, free of charge, to any person obtaining a copy
of the neural net files or training weight files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## Python 运行时与依赖（安装包内置）

安装包用 PyInstaller 打包，内置了 Python 解释器与以下依赖：

| 组件 | 许可 |
|---|---|
| Python 3.8 | PSF License |
| pywebview | BSD 3-Clause |
| pythonnet | MIT |
| WebView2 SDK | Microsoft 许可 |

---

## 开发工具（未随安装包分发）

| 组件 | 用途 | 许可 |
|---|---|---|
| PyInstaller | 打包成 exe | GPL 2.0 with Bootloader Exception |
| Inno Setup | 制作安装程序 | Inno Setup License（允许自由分发产物） |
| Sabaki | 早期验证 SGF / GTP 交互 | MIT |
| jsdom | 前端调试 | MIT |

---

## 说明

- 本仓库**不包含**上述引擎与权重文件（合计约 480 MB）。安装包仅在 Releases 页面提供，
  其中已按上述许可要求附带本声明文件。
- 本项目的原创部分是围棋界面、对局逻辑、引擎封装、打包与安装流程，
  以及 `webapp/`、`legacy/`、`packaging/`、`tools/` 下的全部代码。
- 如有许可疑问，请以各项目官方仓库的 LICENSE 文件为准。
