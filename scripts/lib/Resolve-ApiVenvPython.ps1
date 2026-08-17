function Resolve-ApiVenvPython {
    param(
        [Parameter(Mandatory = $true)][string]$ApiPath
    )

    $candidates = @(
        (Join-Path $ApiPath ".venv/Scripts/python.exe"),
        (Join-Path $ApiPath ".venv/bin/python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    return $null
}