param(
    [string]$Name = "多程序编排 Dashboard",
    [switch]$Admin
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$launcher = if ($Admin) {
    Join-Path $root "launch_dashboard_admin.vbs"
} else {
    Join-Path $root "launch_dashboard.vbs"
}
$iconPath = Join-Path $root "dashboard.ico"

if (-not (Test-Path $launcher)) {
    throw "找不到启动器：$launcher"
}

$desktopDir = [Environment]::GetFolderPath("Desktop")
$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"

$desktopShortcut = Join-Path $desktopDir "$Name.lnk"
$startMenuShortcut = Join-Path $startMenuDir "$Name.lnk"

$shell = New-Object -ComObject WScript.Shell

foreach ($target in @($desktopShortcut, $startMenuShortcut)) {
    $shortcut = $shell.CreateShortcut($target)
    $shortcut.TargetPath = "$env:SystemRoot\System32\wscript.exe"
    $shortcut.Arguments = "`"$launcher`""
    $shortcut.WorkingDirectory = $root
    $shortcut.WindowStyle = 1
    $shortcut.Description = "启动多程序编排 Dashboard"
    if (Test-Path $iconPath) {
        $shortcut.IconLocation = $iconPath
    } else {
        $shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,102"
    }
    $shortcut.Save()
}

Write-Host "已创建快捷方式："
Write-Host "桌面: $desktopShortcut"
Write-Host "开始菜单: $startMenuShortcut"
