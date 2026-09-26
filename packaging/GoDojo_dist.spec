# -*- mode: python ; coding: utf-8 -*-
"""GoDojo 分发版打包 spec

源码取自 D:/GoDojoBuild/src_dist(= patch2 的最新修复 + F 盘 app.py + 前端),
产物 D:/GoDojoBuild/dist/GoDojo/ —— 含 GoDojo.exe 与 web/ 前端。

注意:
  - 分发版外壳默认 --shell edge(Edge 应用模式),不依赖 pywebview。
    但仍打入 pywebview 的 edgechromium 模块,留作 --shell webview 备用。
  - 引擎与权重不在这里打包,由安装包(安装脚本)另外铺设到安装目录。
"""

import os

SRC = 'D:/GoDojoBuild/src_dist'

a = Analysis(
    [SRC + '/app.py'],
    pathex=[SRC],
    binaries=[],
    datas=[(SRC + '/web', 'web'), (SRC + '/assets', 'assets')],
    hiddenimports=['webview.platforms.edgechromium', 'webview.platforms.winforms'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GoDojo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,         # 无窗口模式:绝不能让用户看到黑终端(这是老版本的投诉点)
                           # --warmup 用 runhidden 调用,靠 warmup.result 文件回传结果
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[SRC + '/assets/godogo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GoDojo',
)
