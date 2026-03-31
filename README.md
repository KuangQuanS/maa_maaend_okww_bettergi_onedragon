# Multi Run Dashboard

Windows 桌面面板，用来编排以下四个自动化程序：

- `D:\maa\MAA.exe`
- `D:\maaend\MaaEnd.exe`
- `D:\BetterGI\BetterGI.exe`
- `D:\ok-ww\ok-ww.exe`

这个项目不是去改写这些工具本身，而是负责：

- 启动程序
- 控制顺序
- 监控运行状态
- 读取日志判断完成
- 在面板里展示状态和事件日志

## 当前实现

### 4 个程序的接入方式

- `MAA`
  - 直接启动
  - 自动执行
  - 通过进程退出判定完成
  - 不抢鼠标，可以和其他任务并行

- `MaaEnd`
  - 先启动 `D:\Hypergryph Launcher\games\Arknights Endfield\Endfield.exe`
  - 检测到 `Endfield` 窗口后再等待 15 秒
  - 然后启动 `MaaEnd.exe`
  - 通过日志和窗口状态判定完成
  - 需要管理员权限

- `BetterGI`
  - 通过命令行 `BetterGI.exe --startOneDragon` 启动
  - 读取 BetterGI 日志和 `task_progress` 展示进度
  - 通过日志完成标记和进程退出判定结束

- `OK-WW`
  - 通过命令行 `ok-ww.exe -t 1 -e` 启动
  - 读取 `ok-script.log`
  - 通过任务完成标记、收尾标记、鸣潮进程退出三重条件判定完成

### 调度规则

- `MAA` 可以和其他任务并行
- `MaaEnd`、`BetterGI`、`OK-WW` 视为前台自动化任务，不能互相并行
- 中间栏的“顺序执行”支持自己勾选程序、自己调整顺序
- 如果顺序里包含 `MAA`，它进入运行后，后续前台任务可以继续执行

## 环境要求

- Windows
- Python `3.10+`
- 建议用管理员权限启动面板

必须用管理员启动的典型场景：

- `MaaEnd` 需要拉起 `Endfield.exe`
- 某些第三方工具自身会以管理员方式运行

## 快速开始

### 1. 创建虚拟环境并安装

```powershell
D:\python\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

### 2. 启动面板

管理员启动：

```powershell
.\run_dashboard_admin.bat
```

普通启动：

```powershell
.\run_dashboard.bat
```

也可以直接运行源码入口：

```powershell
.\.venv\Scripts\python.exe -m dashboard_app
```

## 创建桌面和开始菜单快捷方式

建议使用管理员版快捷方式：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_shortcuts.ps1 -Admin -Name "MultiRun Dashboard"
```

生成后会创建：

- 桌面快捷方式
- 开始菜单快捷方式

对应启动器文件：

- [launch_dashboard.vbs](D:/eryouline/launch_dashboard.vbs)
- [launch_dashboard_admin.vbs](D:/eryouline/launch_dashboard_admin.vbs)

## 配置文件

面板自己的数据在 [dashboard_data](D:/eryouline/dashboard_data)。

主要文件：

- [settings.json](D:/eryouline/dashboard_data/settings.json)
  - 程序路径
  - 顺序执行开关
  - 顺序执行顺序
  - OCR 兜底配置

- [workflows.json](D:/eryouline/dashboard_data/workflows.json)
  - 保留历史流程定义

- [runtime](D:/eryouline/dashboard_data/runtime)
  - 运行记录
  - 事件日志
  - 当前活动任务快照

## 日志与完成判定

面板自己的日志：

- [events.log](D:/eryouline/dashboard_data/runtime/events.log)
- [run_records.json](D:/eryouline/dashboard_data/runtime/run_records.json)

第三方工具日志：

- BetterGI: `D:\BetterGI\log`
- OK-WW: `D:\ok-ww\data\apps\ok-ww\working\logs\ok-script.log`

说明：

- `dashboard_data/runtime/` 会按天清理
- 第三方工具自己的日志不会被面板删除

## 常见用法

### 只跑一个程序

直接点左侧卡片的 `Run`。

### 跑多个程序

在中间的“顺序执行”区域：

1. 勾选要执行的程序
2. 调整顺序
3. 点击顶部 `运行顺序`

### 推荐顺序

当前常用顺序可以是：

- `MAA -> BetterGI -> OK-WW -> MaaEnd`

但顺序不是写死的，界面里可以改。

## 开发与测试

离屏 smoke test：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.\.venv\Scripts\python.exe scripts\launch_dashboard.py --smoke-test
```

## 仓库说明

- 源码入口在 [src/dashboard_app](D:/eryouline/src/dashboard_app)
- UI 主窗口在 [main_window.py](D:/eryouline/src/dashboard_app/ui/main_window.py)
- 调度器在 [controller.py](D:/eryouline/src/dashboard_app/controller.py)
- 四个程序的适配器在 [adapters](D:/eryouline/src/dashboard_app/adapters)
