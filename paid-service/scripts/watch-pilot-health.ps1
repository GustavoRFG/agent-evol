param(
    [string]$LocalUrl = "http://localhost:4081/health",
    [string]$PublicUrl = "https://contessa-awkward-vocatively.ngrok-free.dev/health",
    [string]$LogPath,
    [int]$IntervalSeconds = 60,
    [switch]$Once
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $repoRoot "paid-service\logs\pilot-health.jsonl"
}

function Sanitize-Text {
    param([object]$Value, [int]$Limit = 300)
    if ($null -eq $Value) { return "" }
    $text = "$Value"
    $text = $text -replace "[`r`n`t]", " "
    $text = ($text -replace "\s+", " ").Trim()
    if ($text.Length -gt $Limit) { return $text.Substring(0, $Limit) }
    return $text
}

function Invoke-HealthCheck {
    param([string]$Url)
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $headers = @{ "ngrok-skip-browser-warning" = "true" }
        $response = Invoke-WebRequest -Uri $Url -Method GET -Headers $headers -TimeoutSec 10 -UseBasicParsing
        $timer.Stop()
        return [pscustomobject]@{
            url = $Url
            ok = ([int]$response.StatusCode -eq 200)
            status_code = [int]$response.StatusCode
            duration_ms = [int]$timer.ElapsedMilliseconds
            error = ""
        }
    }
    catch {
        $timer.Stop()
        $status = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        return [pscustomobject]@{
            url = $Url
            ok = $false
            status_code = $status
            duration_ms = [int]$timer.ElapsedMilliseconds
            error = Sanitize-Text $_.Exception.Message
        }
    }
}

function Add-HealthRecord {
    param($Record)
    $dir = Split-Path -Parent $LogPath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::AppendAllText(
        $LogPath,
        (($Record | ConvertTo-Json -Compress -Depth 5) + "`n"),
        $encoding
    )
}

function New-HealthRecord {
    param([string]$EventName, $Local, $Public)
    $overall = if ($Local.ok -and $Public.ok) { "healthy" } else { "unhealthy" }
    return [ordered]@{
        timestamp = (Get-Date).ToString("o")
        event = $EventName
        overall_status = $overall
        local_url = $Local.url
        local_status_code = $Local.status_code
        local_duration_ms = $Local.duration_ms
        local_error = $Local.error
        public_url = $Public.url
        public_status_code = $Public.status_code
        public_duration_ms = $Public.duration_ms
        public_error = $Public.error
    }
}

$previousStatus = $null

while ($true) {
    $local = Invoke-HealthCheck $LocalUrl
    $public = Invoke-HealthCheck $PublicUrl
    $currentStatus = if ($local.ok -and $public.ok) { "healthy" } else { "unhealthy" }

    $eventName = $null
    if ($null -eq $previousStatus) {
        $eventName = "initial_status"
    }
    elseif ($previousStatus -eq "healthy" -and $currentStatus -ne "healthy") {
        $eventName = "failure"
    }
    elseif ($previousStatus -ne "healthy" -and $currentStatus -eq "healthy") {
        $eventName = "recovery"
    }
    elseif ($previousStatus -ne $currentStatus) {
        $eventName = "status_transition"
    }

    if ($null -ne $eventName) {
        $record = New-HealthRecord $eventName $local $public
        Add-HealthRecord $record
        Write-Host "$($record.timestamp) | $($record.event) | $($record.overall_status) | local=$($record.local_status_code) public=$($record.public_status_code)"
    }

    $previousStatus = $currentStatus
    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
}
