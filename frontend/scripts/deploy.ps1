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
    aws s3 sync out "s3://$bucket" --exclude '_next/*' --exclude 'pyodide/*' --exclude '*.mjs' --exclude 'status.json' --cache-control 'public,max-age=60' --delete @p
    # test bench: module scripts and wasm need exact types (the site sends nosniff); the runtime is version-pinned
    aws s3 cp out/testbench.worker.mjs "s3://$bucket/testbench.worker.mjs" --content-type 'text/javascript' --cache-control 'public,max-age=60' @p
    aws s3 sync out/pyodide "s3://$bucket/pyodide" --exclude '*' --include '*.mjs' --content-type 'text/javascript' --cache-control 'public,max-age=86400' --delete @p
    aws s3 sync out/pyodide "s3://$bucket/pyodide" --exclude '*' --include '*.wasm' --content-type 'application/wasm' --cache-control 'public,max-age=86400' @p
    aws s3 sync out/pyodide "s3://$bucket/pyodide" --exclude '*.mjs' --exclude '*.wasm' --cache-control 'public,max-age=86400' @p
    aws cloudfront create-invalidation --distribution-id $dist --paths '/*' --query 'Invalidation.Id' --output text @p
    "deployed: $(($outs | Where-Object OutputKey -eq 'SiteUrl').OutputValue)"
} finally { Pop-Location }
