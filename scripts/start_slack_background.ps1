param(
    [switch]$Status
)

$ErrorActionPreference = 'Stop'
$careerRoot = Split-Path -Parent $PSScriptRoot
$careerScript = Join-Path $PSScriptRoot 'run_slack_socket.py'

# Refuse a second receiver, including one started using a relative script path.
# Never stop a process based only on its name.
$careerReceivers = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and
    $_.CommandLine -match '(?:^|[\s"/\\])run_slack_socket\.py(?:[\s"]|$)'
})
if ($Status -or $careerReceivers.Count -gt 0) {
    [pscustomobject]@{
        status = $(if ($careerReceivers.Count -gt 0) { 'process_running' } else { 'stopped' })
        processIds = @($careerReceivers | ForEach-Object { $_.ProcessId })
        scope = 'matching_python_receivers_on_this_computer'
        messageDeliveryVerified = $false
    } | ConvertTo-Json -Compress
    exit 0
}

$careerPython = (Get-Command python -CommandType Application).Source
$careerLogDirectory = Join-Path $careerRoot 'private-data/slack-runtime'
New-Item -ItemType Directory -Path $careerLogDirectory -Force | Out-Null
$careerRunId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$careerOutput = Join-Path $careerLogDirectory ($careerRunId + '.out.log')
$careerError = Join-Path $careerLogDirectory ($careerRunId + '.err.log')
$careerReceiver = Start-Process -FilePath $careerPython `
    -ArgumentList @('-u', ('"' + $careerScript + '"')) `
    -WorkingDirectory $careerRoot -WindowStyle Hidden `
    -RedirectStandardOutput $careerOutput -RedirectStandardError $careerError -PassThru

[pscustomobject]@{
    status = 'process_started'
    processIds = @($careerReceiver.Id)
    stdoutLog = $careerOutput
    stderrLog = $careerError
    messageDeliveryVerified = $false
} | ConvertTo-Json -Compress
