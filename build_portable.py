"""重新打包便携版：python build_portable.py -> ..\\发布\\TimeDeck\\
用 Python 传参而不是 bat 里的长命令行，避开 cmd 的引号与换行续行坑。"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE.parent / "发布"
WORK = HERE / ".build"

EXCLUDES = [
    "QtWebEngineCore", "QtWebEngineWidgets", "QtWebEngine", "QtQuick", "QtQml",
    "QtQuickWidgets", "Qt3DCore", "QtCharts", "QtDataVisualization", "QtTest",
    "QtPdf", "QtMultimedia", "QtMultimediaWidgets", "QtDesigner", "QtUiTools",
    "QtBluetooth", "QtSerialPort", "QtSql", "QtPositioning", "QtLocation",
    "QtRemoteObjects", "QtSensors", "QtTextToSpeech", "QtHelp", "QtNetwork",
    "QtSvg", "QtSvgWidgets",
]


def main() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed", "--name", "TimeDeck",
        "--icon", str(HERE / "app.ico"),
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
    ]
    args += [f"--exclude-module=PySide6.{name}" for name in EXCLUDES]
    args.append(str(HERE / "main.py"))

    code = subprocess.call(args, cwd=str(HERE))
    exe = DIST / "TimeDeck" / "TimeDeck.exe"
    if code != 0 or not exe.exists():
        print(f"[X] 打包失败，退出码 {code}")
        return code or 1

    guide = HERE / "使用说明.txt"
    if guide.exists():
        shutil.copy2(guide, exe.parent / guide.name)
    print(f"[OK] 打包完成：{exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
