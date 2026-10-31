param(
    [string]$Server = "loktionov@178.124.129.166",
    [string]$Key = "$env:USERPROFILE\.ssh\opencode_vps",
    [string]$RemotePath = "/home/loktionov/ttn_bot",
    [string]$Service = "ttn_bot.service",
    [string]$Branch = "main",
    [switch]$SkipPush
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Find-Git {
    $command = Get-Command git -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $patterns = @(
        "$env:LOCALAPPDATA\GitHubDesktop\app-*\resources\app\git\cmd\git.exe",
        "$env:ProgramFiles\Git\cmd\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe"
    )
    foreach ($pattern in $patterns) {
        $found = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }
    throw "git.exe not found"
}

if (-not (Test-Path -LiteralPath $Key)) {
    throw "SSH key not found: $Key"
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot "deploy_remote.sh"))) {
    throw "deploy_remote.sh not found next to deploy.ps1"
}
foreach ($value in @($RemotePath, $Service, $Branch)) {
    if ($value -match "'") {
        throw "Remote arguments must not contain single quotes: $value"
    }
}

$git = Find-Git
$branchNow = (& $git rev-parse --abbrev-ref HEAD).Trim()
if ($branchNow -ne $Branch) {
    throw "Current branch is '$branchNow', expected '$Branch'"
}

$status = & $git status --porcelain
if ($status) {
    $status | Write-Host
    throw "Working tree is not clean. Commit changes before deploying."
}

$commit = (& $git rev-parse HEAD).Trim()
Write-Host "Deploying commit $commit from branch $Branch"

if (-not $SkipPush) {
    & $git push origin $Branch
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed"
    }
}

$remoteId = [guid]::NewGuid().ToString("N")
$remoteScript = "/tmp/ttn_deploy_$remoteId.sh"
$exitCode = 1

try {
    Write-Host "Uploading deploy script to ${Server}:$remoteScript"
    & scp -i $Key -q (Join-Path $PSScriptRoot "deploy_remote.sh") "${Server}:$remoteScript"
    if ($LASTEXITCODE -ne 0) {
        throw "scp failed"
    }

    & ssh -i $Key $Server "bash -n $remoteScript"
    if ($LASTEXITCODE -ne 0) {
        throw "Remote deploy script syntax check failed"
    }

    & ssh -i $Key $Server "bash $remoteScript '$commit' '$RemotePath' '$Service' '$Branch'"
    $exitCode = $LASTEXITCODE
}
finally {
    & ssh -i $Key $Server "rm -f $remoteScript" | Out-Null
}

if ($exitCode -ne 0) {
    throw "Deploy failed with exit code $exitCode"
}

Write-Host "Deploy finished successfully: $commit"
