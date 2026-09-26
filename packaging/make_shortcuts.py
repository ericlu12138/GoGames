# -*- coding: utf-8 -*-
"""建桌面 + 开始菜单快捷方式,直指 F 盘发布目录(不复制文件到 C 盘)"""
import os
import win32com.client

EXE = r"F:\围棋\发布\GoDojo\GoDojo.exe"
DIR = r"F:\围棋\发布\GoDojo"

assert os.path.exists(EXE), "找不到 " + EXE

ws = win32com.client.Dispatch("WScript.Shell")

desktop = ws.SpecialFolders("Desktop")
start = ws.SpecialFolders("Programs")   # 当前用户开始菜单的 Programs 目录

targets = [os.path.join(desktop, "GoDojo.lnk"),
           os.path.join(start, "GoDojo.lnk")]

for p in targets:
    s = ws.CreateShortcut(p)
    s.TargetPath = EXE
    s.WorkingDirectory = DIR
    s.IconLocation = EXE + ",0"
    s.Description = "GoDojo 围棋陪练"
    s.Save()
    print("已创建: %s" % p)

# 回读验证
for p in targets:
    c = ws.CreateShortcut(p)
    print("  %s -> %s  目标存在=%s" % (os.path.basename(p), c.TargetPath,
                                       os.path.exists(c.TargetPath)))
print("DONE")
