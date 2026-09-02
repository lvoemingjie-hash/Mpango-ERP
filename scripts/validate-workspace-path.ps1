[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('worktree', 'evidence', 'handoff', 'scratch', 'archive', 'codex-managed-worktree')]
    [string]$Purpose,

    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string]$WorkspaceRoot,

    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$isWindowsHost = $env:OS -eq 'Windows_NT'
$comparison = if ($isWindowsHost) {
    [StringComparison]::OrdinalIgnoreCase
} else {
    [StringComparison]::Ordinal
}

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    $WorkspaceRoot = if ($isWindowsHost) {
        Join-Path $HOME 'MPANGO ERP'
    } else {
        Join-Path $HOME 'Documents/Codex/Mpango-ERP'
    }
}

$workspaceFull = [IO.Path]::GetFullPath($WorkspaceRoot)
$allowedRoot = switch ($Purpose) {
    'worktree' { Join-Path $workspaceFull 'worktrees' }
    'evidence' { Join-Path $workspaceFull 'evidence' }
    'handoff' { Join-Path $workspaceFull 'handoffs' }
    'scratch' { Join-Path $workspaceFull 'scratch' }
    'archive' { Join-Path $workspaceFull 'archive' }
    'codex-managed-worktree' { Join-Path (Join-Path $HOME '.codex') 'worktrees' }
}

$allowedFull = [IO.Path]::GetFullPath($allowedRoot).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$targetFull = [IO.Path]::GetFullPath($Path).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$allowedPrefix = $allowedFull + [IO.Path]::DirectorySeparatorChar

$allowed = $targetFull.StartsWith($allowedPrefix, $comparison)
$category = if ($allowed) { 'APPROVED_CANONICAL_DESCENDANT' } else { 'OUTSIDE_APPROVED_PURPOSE_ROOT' }

if ($allowed) {
    $cursor = $targetFull
    while ($cursor.StartsWith($allowedPrefix, $comparison) -or $cursor.Equals($allowedFull, $comparison)) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                $allowed = $false
                $category = 'REPARSE_POINT_IN_TARGET_CHAIN'
                break
            }
        }

        if ($cursor.Equals($allowedFull, $comparison)) {
            break
        }

        $parent = Split-Path -Path $cursor -Parent
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $cursor) {
            $allowed = $false
            $category = 'PATH_PARENT_RESOLUTION_FAILED'
            break
        }
        $cursor = [IO.Path]::GetFullPath($parent).TrimEnd(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        )
    }
}

$result = [ordered]@{
    schema_version = 1
    purpose = $Purpose
    proposed_path = $targetFull
    approved_root = $allowedFull
    allowed = $allowed
    category = $category
    creates_or_moves_files = $false
}

if ($Json) {
    $result | ConvertTo-Json -Depth 3
} else {
    Write-Output "Workspace path validation"
    Write-Output "  Purpose: $Purpose"
    Write-Output "  Proposed path: $targetFull"
    Write-Output "  Approved root: $allowedFull"
    Write-Output "  Allowed: $allowed"
    Write-Output "  Category: $category"
}

if (-not $allowed) {
    exit 32
}
