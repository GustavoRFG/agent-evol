param(
    [string]$LogPath,
    [int]$InitialCount = 25,
    [switch]$NoFollow
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $repoRoot "paid-service\logs\http-access.jsonl"
}

function Convert-LogLine {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return $null }
    try {
        return $Line | ConvertFrom-Json
    }
    catch {
        return [pscustomobject]@{
            timestamp = ""
            event = "request_error"
            method = ""
            path = ""
            status_code = $null
            status_text = "Unparseable Log Line"
            client_ip = ""
            proxy_ip = ""
            user_agent = ""
            payment_present = $false
        }
    }
}

function Get-StatusLabel {
    param($Entry)
    if ($null -eq $Entry.status_code -or "$($Entry.status_code)" -eq "") {
        return "NO STATUS"
    }
    $code = [int]$Entry.status_code
    switch ($code) {
        200 { return "200 OK" }
        400 { return "400 Bad Request" }
        402 { return "402 Payment Required" }
        404 { return "404 Not Found" }
        default {
            $text = "$($Entry.status_text)".Trim()
            if ([string]::IsNullOrWhiteSpace($text)) { $text = "Status" }
            return "$code $text"
        }
    }
}

function Get-StatusCodeNumber {
    param($Entry)
    if ($null -eq $Entry.status_code -or "$($Entry.status_code)" -eq "") {
        return 0
    }
    return [int]$Entry.status_code
}

function Test-RelevantEvent {
    param($Entry)
    $event = "$($Entry.event)"
    return $event -in @("request_finished", "request_closed_before_finish", "request_error", "")
}

function Format-Entry {
    param($Entry)
    if (-not (Test-RelevantEvent $Entry)) { return $null }

    $status = Get-StatusLabel $Entry
    $route = "$($Entry.method) $($Entry.path)".Trim()
    $client = "$($Entry.client_ip)".Trim()
    if ([string]::IsNullOrWhiteSpace($client)) { $client = "$($Entry.proxy_ip)".Trim() }
    if ([string]::IsNullOrWhiteSpace($client)) { $client = "$($Entry.remote_addr)".Trim() }
    if ([string]::IsNullOrWhiteSpace($client)) { $client = "-" }
    $agent = "$($Entry.user_agent)".Trim()
    if ([string]::IsNullOrWhiteSpace($agent)) { $agent = "-" }

    $labels = @()
    if ($Entry.event -eq "request_closed_before_finish") { $labels += "INTERRUPTED" }
    if ($Entry.event -eq "request_error") { $labels += "ERROR" }
    $statusCode = Get-StatusCodeNumber $Entry
    if ($Entry.method -eq "POST" -and $Entry.path -eq "/paid/evaluate-agent-run" -and $statusCode -eq 402) {
        $labels += "UNPAID_GATE"
    }
    if ($Entry.method -eq "POST" -and $Entry.path -eq "/paid/evaluate-agent-run" -and $statusCode -eq 200 -and $Entry.payment_present -eq $true) {
        $labels += "PAID"
    }
    $labelText = ""
    if ($labels.Count -gt 0) { $labelText = " | " + ($labels -join ",") }

    return "$($Entry.timestamp) | $status | $route | $client | $agent$labelText"
}

function Show-Line {
    param([string]$Line)
    $entry = Convert-LogLine $Line
    if ($null -eq $entry) { return }
    $formatted = Format-Entry $entry
    if (-not [string]::IsNullOrWhiteSpace($formatted)) {
        Write-Host $formatted
    }
}

Write-Host "AgentEval Forge seller-side live HTTP monitor"
Write-Host "Log: $LogPath"
Write-Host "Source: paid-service/logs/http-access.jsonl (ngrok Inspector not used)"
Write-Host ""

if (-not (Test-Path -LiteralPath $LogPath)) {
    Write-Host "No access log yet."
    if ($NoFollow) { exit 0 }
    while (-not (Test-Path -LiteralPath $LogPath)) {
        Start-Sleep -Seconds 1
    }
}

Write-Host "Latest $InitialCount finished requests"
Get-Content -LiteralPath $LogPath |
    ForEach-Object { Convert-LogLine $_ } |
    Where-Object {
        $null -ne $_ -and (
            $_.event -eq "request_finished" -or
            ([string]::IsNullOrWhiteSpace("$($_.event)") -and $null -ne $_.status_code)
        )
    } |
    Select-Object -Last $InitialCount |
    ForEach-Object {
        $formatted = Format-Entry $_
        if (-not [string]::IsNullOrWhiteSpace($formatted)) { Write-Host $formatted }
    }

if ($NoFollow) { exit 0 }

Get-Content -LiteralPath $LogPath -Wait -Tail 0 | ForEach-Object {
    Show-Line $_
}
