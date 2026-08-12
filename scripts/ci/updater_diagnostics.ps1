function ConvertTo-ScrubbedUpdaterText {
    param(
        [Parameter(Mandatory)][AllowEmptyString()][string]$Text,
        [hashtable]$PathReplacements = @{}
    )

    $result = $Text
    foreach ($entry in $PathReplacements.GetEnumerator()) {
        if ($entry.Key) {
            $result = [regex]::Replace(
                $result,
                [regex]::Escape([string]$entry.Key),
                [System.Text.RegularExpressions.MatchEvaluator]{ param($match) [string]$entry.Value },
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )
        }
    }

    # Redact the complete credential, including optional Bearer prefixes and quoted JSON values.
    $result = [regex]::Replace(
        $result,
        '(?im)("[^"\r\n]*(?:authorization|token|secret)[^"\r\n]*"\s*:\s*")([^"]*)(")',
        '$1[redacted]$3'
    )
    $result = [regex]::Replace(
        $result,
        "(?im)('[^'\r\n]*(?:authorization|token|secret)[^'\r\n]*'\s*:\s*')([^']*)(')",
        '$1[redacted]$3'
    )
    $result = [regex]::Replace(
        $result,
        '(?im)(["'']?authorization["'']?\s*[:=]\s*["'']?)(?:bearer\s+)?([^"'',;\s]+)(["'']?)',
        '$1[redacted]$3'
    )
    $result = [regex]::Replace(
        $result,
        '(?im)(["'']?[A-Za-z0-9_]*(?:token|secret)[A-Za-z0-9_]*["'']?\s*[:=]\s*["'']?)([^"'',;&\s]+)(["'']?)',
        '$1[redacted]$3'
    )
    return $result
}
