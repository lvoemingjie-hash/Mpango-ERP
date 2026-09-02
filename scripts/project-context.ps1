[CmdletBinding()]
param(
    [switch]$Refresh,
    [switch]$Json,
    [switch]$IncludeWorktrees
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-GitAt {
    param(
        [Parameter(Mandatory = $true)][string]$Repository,
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [switch]$AllowFailure
    )

    $output = @(& git -C $Repository @GitArgs 2>&1)
    $exitCode = $LASTEXITCODE
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $exitCode"
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Lines = @($output | ForEach-Object { $_.ToString() })
    }
}

function Get-FirstLine {
    param([Parameter(Mandatory = $true)]$Result)
    if ($Result.Lines.Count -eq 0) { return $null }
    return $Result.Lines[0].Trim()
}

function Get-WorktreeCategory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $normalized = $Path.Replace('\', '/').ToLowerInvariant()
    if ($normalized.Contains('/mpango erp/worktrees/')) { return 'canonical-worktrees' }
    if ($normalized.Contains('/.codex/worktrees/')) { return 'codex-managed' }
    if ($normalized.Contains('/appdata/local/temp/')) { return 'temp-legacy' }
    if ($normalized.Contains('/mpango erp/')) { return 'mpango-root-legacy' }
    return 'other'
}

$repoProbe = @(& git rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0 -or $repoProbe.Count -eq 0) {
    throw 'Run this script from inside an Mpango ERP Git worktree.'
}

$repoRoot = (Resolve-Path -LiteralPath $repoProbe[0].ToString().Trim()).Path

if ($Refresh) {
    $fetch = Invoke-GitAt -Repository $repoRoot -GitArgs @('fetch', '--all', '--prune')
}

$statePath = Join-Path $repoRoot 'docs/current/state.json'
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "Missing canonical state file: $statePath"
}
$state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json

$head = Get-FirstLine (Invoke-GitAt -Repository $repoRoot -GitArgs @('rev-parse', 'HEAD'))
$branch = Get-FirstLine (Invoke-GitAt -Repository $repoRoot -GitArgs @('rev-parse', '--abbrev-ref', 'HEAD'))
$statusLines = (Invoke-GitAt -Repository $repoRoot -GitArgs @('status', '--porcelain')).Lines
$protected = Invoke-GitAt -Repository $repoRoot -GitArgs @(
    'rev-parse', 'refs/remotes/origin/product-dev-recovered'
) -AllowFailure
$protectedTip = if ($protected.ExitCode -eq 0) { Get-FirstLine $protected } else { $null }

$worktreeLines = (Invoke-GitAt -Repository $repoRoot -GitArgs @(
    'worktree', 'list', '--porcelain'
)).Lines
$worktrees = @()
foreach ($line in $worktreeLines) {
    if ($line.StartsWith('worktree ')) {
        $path = $line.Substring(9)
        $worktrees += [pscustomobject]@{
            path = $path
            category = Get-WorktreeCategory -Path $path
        }
    }
}

$worktreeGroups = @{}
foreach ($item in $worktrees) {
    if (-not $worktreeGroups.ContainsKey($item.category)) {
        $worktreeGroups[$item.category] = 0
    }
    $worktreeGroups[$item.category] += 1
}

$remoteRefCount = (Invoke-GitAt -Repository $repoRoot -GitArgs @(
    'for-each-ref', '--format=%(refname)', 'refs/remotes/origin'
)).Lines.Count
$localBranchCount = (Invoke-GitAt -Repository $repoRoot -GitArgs @(
    'for-each-ref', '--format=%(refname)', 'refs/heads'
)).Lines.Count

$requiredDocs = @(
    'START-HERE.md',
    'docs/current/STATE.md',
    'docs/current/state.json',
    'docs/architecture/OVERVIEW.md',
    'docs/operations/RUNBOOK.md',
    'docs/governance/EVIDENCE.md',
    'docs/navigation/ACTIVE-WORK.md',
    'docs/navigation/WORKSPACE-HYGIENE.md'
)
$missingDocs = @($requiredDocs | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $repoRoot $_) -PathType Leaf)
})

$recordedBaseline = $state.current_product_baseline.base_sha
$baselineMatches = $null -ne $protectedTip -and $recordedBaseline -eq $protectedTip

$result = [ordered]@{
    schema_version = $state.schema_version
    project = 'Mpango-ERP'
    repository = $repoRoot
    branch = $branch
    head = $head
    clean = $statusLines.Count -eq 0
    changed_or_untracked_count = $statusLines.Count
    protected_product_tip = $protectedTip
    recorded_product_baseline = $recordedBaseline
    recorded_baseline_matches_local_remote_ref = $baselineMatches
    snapshot_at = $state.snapshot_at
    alembic_head = $state.current_product_baseline.alembic_head
    delivery_status = $state.current_product_baseline.delivery_status
    active_tracks = @($state.active_tracks)
    worktree_count = $worktrees.Count
    worktree_categories = $worktreeGroups
    remote_ref_count = $remoteRefCount
    local_branch_count = $localBranchCount
    missing_navigation_docs = $missingDocs
}

if ($IncludeWorktrees) {
    $result.worktrees = $worktrees
}

if ($Json) {
    $result | ConvertTo-Json -Depth 10
    exit 0
}

Write-Output 'Mpango ERP project context'
Write-Output "  Repository: $repoRoot"
Write-Output "  Branch: $branch"
Write-Output "  HEAD: $head"
Write-Output "  Worktree clean: $($result.clean) (changed/untracked: $($statusLines.Count))"
Write-Output "  Protected tip: $protectedTip"
Write-Output "  Recorded baseline: $recordedBaseline"
Write-Output "  Baseline matches local origin ref: $baselineMatches"
Write-Output "  Alembic head: $($result.alembic_head)"
Write-Output "  Delivery status: $($result.delivery_status)"
Write-Output "  Registered worktrees: $($worktrees.Count)"
Write-Output "  Remote refs: $remoteRefCount; local branches: $localBranchCount"

Write-Output '  Active tracks:'
foreach ($track in $state.active_tracks) {
    $candidate = if ($null -eq $track.candidate) {
        '-'
    } else {
        $track.candidate.evidence_sha
    }
    Write-Output "    $($track.id): $($track.status); candidate=$candidate; next=$($track.next_gate)"
}

if ($missingDocs.Count -gt 0) {
    Write-Warning "Missing navigation documents: $($missingDocs -join ', ')"
}
if (-not $baselineMatches) {
    Write-Warning 'Recorded current truth is stale relative to the local origin ref. STOP and reconcile it.'
}

if ($IncludeWorktrees) {
    Write-Output '  Worktrees:'
    foreach ($item in $worktrees) {
        Write-Output "    [$($item.category)] $($item.path)"
    }
}
