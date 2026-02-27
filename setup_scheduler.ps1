# Trading Agent - Windows Task Scheduler Setup
# Run this script as Administrator to set up daily execution

param(
    [string]$TaskName = "TradingAgent-DailyRun",
    [string]$RunTime = "07:00",
    [switch]$Remove
)

$ProjectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonPath = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectPath "src\main.py"

# Check if removing task
if ($Remove) {
    Write-Host "Removing scheduled task '$TaskName'..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Task removed."
    exit 0
}

# Check if virtual environment exists
if (-not (Test-Path $PythonPath)) {
    Write-Host "Error: Virtual environment not found at $PythonPath" -ForegroundColor Red
    Write-Host "Please create it first:"
    Write-Host "  cd $ProjectPath"
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\activate"
    Write-Host "  pip install -r requirements.txt"
    exit 1
}

Write-Host "Setting up scheduled task '$TaskName'..."
Write-Host "  Python: $PythonPath"
Write-Host "  Script: $ScriptPath"
Write-Host "  Run Time: $RunTime (weekdays)"

# Create the scheduled task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $ProjectPath

# Create trigger for specified time on weekdays
$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At $RunTime

# Create settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# Check if task already exists
$ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($ExistingTask) {
    Write-Host "Task already exists. Updating..."
    Set-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings
} else {
    Write-Host "Creating new task..."
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "Daily trading data analysis and recommendations"
}

Write-Host ""
Write-Host "Task '$TaskName' configured successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "To test the task immediately:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To view task status:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
Write-Host ""
Write-Host "To remove the task:"
Write-Host "  .\setup_scheduler.ps1 -Remove"
