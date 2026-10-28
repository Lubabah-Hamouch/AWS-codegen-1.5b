<#
Build the static export and publish it to the codegen-frontend bucket behind CloudFront.

  .\frontend\scripts\deploy.ps1

Webpack, not Turbopack: Turbopack's export injects an inline bootstrap <script>, which the site's CSP
(script-src 'self') blocks. status.json is excluded from the sync: it belongs to the kill-switch tooling.
#>
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$p = '--profile', 'codegen-spike', '--region', 'eu-north-1'
Push-Location (Join-Path $PSScriptRoot '..')
try {
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'build failed' }
    $inline = Select-String -Path out\*.html, out\*\*.html -Pattern '<script(?![^>]*src=)(?![^>]*application/json)' -AllMatches
    if ($inline) { throw "inline <script> in the export would be blocked by the CSP: $($inline[0])" }
    $outs = aws cloudformation describe-stacks --stack-name codegen-frontend --query 'Stacks[0].Outputs' --output json @p | ConvertFrom-Json
    $bucket = ($outs | Where-Object OutputKey -eq 'BucketName').OutputValue
    $dist = ($outs | Where-Object OutputKey -eq 'DistributionId').OutputValue
    # hashed assets: cache for a year; HTML and replays: revalidate
    aws s3 sync out/_next "s3://$bucket/_next" --cache-control 'public,max-age=31536000,immutable' --delete @p
    aws s3 sync out "s3://$bucket" --exclude '_next/*' --exclude 'status.json' --cache-control 'public,max-age=60' --delete @p
    aws cloudfront create-invalidation --distribution-id $dist --paths '/*' --query 'Invalidation.Id' --output text @p
    "deployed: $(($outs | Where-Object OutputKey -eq 'SiteUrl').OutputValue)"
} finally { Pop-Location }
