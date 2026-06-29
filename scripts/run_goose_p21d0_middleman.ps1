param(
    [string]$RepoRoot = "C:\Users\Jeff0\MPANGO ERP\platform-group1-shared-memory-sync-2026-05-20",
    [string]$GooseExe = "C:\Users\Jeff0\.local\bin\goose.exe"
)

$ErrorActionPreference = "Stop"

function Read-TextFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required file not found: $Path"
    }
    return Get-Content -LiteralPath $Path -Raw
}

function Write-Utf8NoBom([string]$Path, [string]$Value) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Extract-JsonObject([string]$Text) {
    $trimmed = $Text.Trim()
    if ($trimmed.StartsWith('```')) {
        $trimmed = $trimmed -replace '^\s*```(?:json)?\s*', ''
        $trimmed = $trimmed -replace '\s*```\s*$', ''
    }
    $start = $trimmed.IndexOf('{')
    $end = $trimmed.LastIndexOf('}')
    if ($start -lt 0 -or $end -lt $start) {
        throw "Goose did not return a JSON object."
    }
    return $trimmed.Substring($start, $end - $start + 1)
}

if (-not (Test-Path -LiteralPath $GooseExe)) {
    throw "Goose executable not found: $GooseExe"
}

$contextPath = Join-Path $RepoRoot ".review\PROJECT_CONTEXT.md"
$taskPath = Join-Path $RepoRoot ".review\tasks\P21-D0.task.json"
$outboxPath = Join-Path $RepoRoot ".review\outbox\P21-D0.to-claude.md"
$auditPath = Join-Path $RepoRoot ".review\audit\P21-D0.audit.md"
$statePath = Join-Path $RepoRoot ".review\state\goose-runner-state.json"

$context = Read-TextFile $contextPath
$task = Read-TextFile $taskPath
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$prompt = @(
    "You are Goose Middleman for the Mpango ERP SaaS platform track.",
    "",
    "You are a dispatcher/recorder only. You are not a developer, reviewer, gatekeeper, or merger. Codex CTO keeps final authority.",
    "",
    "This is a SHADOW pilot. Do not dispatch Claude. Do not touch runtime code. Do not merge. Do not push. Do not write final approval markers.",
    "",
    "The deterministic wrapper has already read the project context and task packet for you. You must now return exactly one JSON object and nothing else.",
    "",
    "PROJECT_CONTEXT:",
    "<<<PROJECT_CONTEXT",
    $context,
    "PROJECT_CONTEXT",
    "",
    "TASK_PACKET:",
    "<<<TASK_PACKET",
    $task,
    "TASK_PACKET",
    "",
    "Return exactly this JSON shape:",
    "{",
    '  "outbox_markdown": "Claude-ready Markdown handoff packet with headings: SHADOW ONLY, Objective, Scope, Forbidden Changes, Validation Gates, Stop Conditions, Result Report Format, Next Action. At least 700 characters.",',
    ('  "audit_markdown": "Audit log Markdown. Must include task_id, UTC timestamp ' + $now + ', files read, files written, mode=shadow, no dispatch, no runtime code touched, no merge/push attempted, next action=Codex/user review. At least 250 characters.",'),
    '  "state": {',
    '    "task_id": "P21-D0",',
    '    "status": "shadow_complete",',
    '    "mode": "shadow",',
    '    "outbox_path": ".review/outbox/P21-D0.to-claude.md",',
    '    "audit_path": ".review/audit/P21-D0.audit.md",',
    '    "next_action": "Codex/user review"',
    "  }",
    "}",
    "",
    "No markdown fences. No commentary. JSON only."
) -join [Environment]::NewLine

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("goose-p21d0-" + [System.Guid]::NewGuid().ToString("N") + ".md")
Write-Utf8NoBom $tmp $prompt

Push-Location $RepoRoot
try {
    $output = & $GooseExe run `
        --instructions $tmp `
        --no-profile `
        --no-session `
        --max-turns 4 `
        --max-tool-repetitions 1 `
        --quiet `
        --output-format text
    if ($LASTEXITCODE -ne 0) {
        throw "Goose exited with code $LASTEXITCODE"
    }

    $jsonText = Extract-JsonObject ($output -join "`n")
    $result = $jsonText | ConvertFrom-Json

    if (-not $result.outbox_markdown -or -not $result.audit_markdown -or -not $result.state) {
        throw "Goose JSON is missing required fields."
    }

    $outboxText = ([string]$result.outbox_markdown) -replace 'Gemini', 'Goose'
    $auditText = ([string]$result.audit_markdown) -replace 'Gemini', 'Goose'
    $requiredOutboxPhrases = @(
        "SHADOW ONLY",
        "Objective",
        "Scope",
        "Forbidden Changes",
        "Validation Gates",
        "Stop Conditions",
        "Result Report Format",
        "Next Action"
    )
    foreach ($phrase in $requiredOutboxPhrases) {
        if ($outboxText -notmatch [regex]::Escape($phrase)) {
            throw "Goose outbox is missing required phrase: $phrase"
        }
    }
    if ($outboxText.Length -lt 700) {
        throw "Goose outbox is too short: $($outboxText.Length) characters"
    }
    if ($outboxText -match "Gemini" -or $auditText -match "Gemini") {
        throw "Goose output contains incorrect worker label: Gemini"
    }
    foreach ($phrase in @("P21-D0", "mode", "shadow", "no dispatch", "no runtime code", "no merge")) {
        if ($auditText -notmatch [regex]::Escape($phrase)) {
            throw "Goose audit is missing required phrase: $phrase"
        }
    }

    Write-Utf8NoBom $outboxPath $outboxText
    Write-Utf8NoBom $auditPath $auditText
    Write-Utf8NoBom $statePath ($result.state | ConvertTo-Json -Depth 8)

    $required = @($outboxPath, $auditPath, $statePath)
    foreach ($path in $required) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Required output was not created: $path"
        }
    }
    exit 0
}
finally {
    Pop-Location
    Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
}
