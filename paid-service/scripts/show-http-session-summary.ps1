param(
    [datetime]$Since,
    [string]$LogPath
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $repoRoot "paid-service\logs\http-access.jsonl"
}

function Convert-LogLine {
    param([string]$Line)
    if ([string]::IsNullOrWhiteSpace($Line)) { return $null }
    try { return $Line | ConvertFrom-Json }
    catch { return $null }
}

function Get-EventName {
    param($Entry)
    $event = "$($Entry.event)"
    if ([string]::IsNullOrWhiteSpace($event) -and $null -ne $Entry.status_code) {
        return "request_finished"
    }
    return $event
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

function Get-Route {
    param($Entry)
    return "$($Entry.method) $($Entry.path)".Trim()
}

function Get-ClientIp {
    param($Entry)
    $client = "$($Entry.client_ip)".Trim()
    if ([string]::IsNullOrWhiteSpace($client)) { $client = "$($Entry.proxy_ip)".Trim() }
    if ([string]::IsNullOrWhiteSpace($client)) { $client = "$($Entry.remote_addr)".Trim() }
    if ([string]::IsNullOrWhiteSpace($client)) { return "-" }
    return $client
}

function Show-Group {
    param(
        [string]$Title,
        [object[]]$Rows,
        [scriptblock]$Key
    )
    Write-Host ""
    Write-Host $Title
    if ($Rows.Count -eq 0) {
        Write-Host "  (none)"
        return
    }
    $Rows |
        Group-Object -Property $Key |
        Sort-Object -Property Count -Descending |
        Select-Object Count, Name |
        Format-Table -AutoSize
}

if (-not (Test-Path -LiteralPath $LogPath)) {
    Write-Host "No seller-side access log found at: $LogPath"
    exit 0
}

$entries = Get-Content -LiteralPath $LogPath |
    ForEach-Object { Convert-LogLine $_ } |
    Where-Object { $null -ne $_ }

if ($PSBoundParameters.ContainsKey("Since")) {
    $entries = $entries | Where-Object {
        try { [datetime]$_.timestamp -ge $Since } catch { $false }
    }
}

$entries = @($entries)
$finished = @($entries | Where-Object { (Get-EventName $_) -eq "request_finished" })
$closed = @($entries | Where-Object { (Get-EventName $_) -eq "request_closed_before_finish" })
$errors = @($entries | Where-Object { (Get-EventName $_) -eq "request_error" })
$started = @($entries | Where-Object { (Get-EventName $_) -eq "request_started" })

$timestamps = @($entries | ForEach-Object { try { [datetime]$_.timestamp } catch { $null } } | Where-Object { $null -ne $_ } | Sort-Object)

Write-Host "AgentEval Forge seller-side HTTP session summary"
Write-Host "Log: $LogPath"
if ($PSBoundParameters.ContainsKey("Since")) {
    Write-Host "Since: $($Since.ToString("o"))"
}
if ($timestamps.Count -gt 0) {
    Write-Host "Range: $($timestamps[0].ToString("o")) -> $($timestamps[$timestamps.Count - 1].ToString("o"))"
}
else {
    Write-Host "Range: (no parseable timestamps)"
}
Write-Host "Total finished requests: $($finished.Count)"

Show-Group "By method" $finished { $_.method }
Show-Group "By status" $finished { Get-StatusLabel $_ }
Show-Group "By route" $finished { Get-Route $_ }
Show-Group "By client_ip" $finished { Get-ClientIp $_ }
Show-Group "By user_agent" $finished { if ([string]::IsNullOrWhiteSpace("$($_.user_agent)")) { "-" } else { $_.user_agent } }

Write-Host ""
Write-Host "Unpaid gate POST /paid/evaluate-agent-run -> 402"
$finished |
    Where-Object { $_.method -eq "POST" -and $_.path -eq "/paid/evaluate-agent-run" -and [int]$_.status_code -eq 402 } |
    Select-Object timestamp, request_id, @{Name = "client_ip"; Expression = { Get-ClientIp $_ } }, user_agent, duration_ms |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Paid POST /paid/evaluate-agent-run -> 200 with payment_present=true"
$finished |
    Where-Object { $_.method -eq "POST" -and $_.path -eq "/paid/evaluate-agent-run" -and [int]$_.status_code -eq 200 -and $_.payment_present -eq $true } |
    Select-Object timestamp, request_id, @{Name = "client_ip"; Expression = { Get-ClientIp $_ } }, user_agent, duration_ms |
    Format-Table -AutoSize

$startedWithoutTerminal = @()
$entries |
    Where-Object { -not [string]::IsNullOrWhiteSpace("$($_.request_id)") } |
    Group-Object request_id |
    ForEach-Object {
        $events = @($_.Group | ForEach-Object { Get-EventName $_ })
        if ($events -contains "request_started" -and -not (
            $events -contains "request_finished" -or
            $events -contains "request_closed_before_finish" -or
            $events -contains "request_error"
        )) {
            $first = $_.Group | Select-Object -First 1
            $startedWithoutTerminal += [pscustomobject]@{
                request_id = $_.Name
                timestamp = $first.timestamp
                method = $first.method
                path = $first.path
                client_ip = Get-ClientIp $first
            }
        }
    }

Write-Host ""
Write-Host "Lifecycle anomalies"
Write-Host "Started without terminal event: $($startedWithoutTerminal.Count)"
$startedWithoutTerminal | Format-Table -AutoSize
Write-Host "Closed before finish: $($closed.Count)"
$closed | Select-Object timestamp, request_id, method, path, @{Name = "client_ip"; Expression = { Get-ClientIp $_ } }, duration_ms | Format-Table -AutoSize
Write-Host "Request errors: $($errors.Count)"
$errors | Select-Object timestamp, request_id, method, path, status_code, status_text, @{Name = "client_ip"; Expression = { Get-ClientIp $_ } }, duration_ms | Format-Table -AutoSize
