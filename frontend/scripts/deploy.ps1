<#
Publish the static export to the codegen-frontend bucket behind CloudFront.

  .\frontend\scripts\deploy.ps1                                   build here, then publish
  .\frontend\scripts\deploy.ps1 -From frontend-out-<sha>.zip      publish a CI build (the artifact zip, or its unzipped folder)
  .\frontend\scripts\deploy.ps1 -From <zip or folder> -DryRun      list what would change; uploads nothing, no invalidation

Webpack, not Turbopack: Turbopack's export injects an inline bootstrap <script>, which the site's CSP
(script-src 'self') blocks; scripts/check-csp.mjs refuses such an export. status.json is excluded from the sync: it
belongs to the kill-switch tooling.
#>
param([string]$From, [switch]$DryRun)
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$p = '--profile', 'codegen-spike', '--region', 'eu-north-1'
$s3 = @(); if ($DryRun) { $s3 = @('--dryrun') }
$from = if ($From) { (Resolve-Path $From).Path }
Push-Location (Join-Path $PSScriptRoot '..')
$unzipped = $null
try {
    if (-not $from) {
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'build failed' }
        $out = 'out'
    } elseif ($from -like '*.zip') {
        $unzipped = Join-Path ([IO.Path]::GetTempPath()) "frontend-out-$([guid]::NewGuid())"
        Expand-Archive $from $unzipped
        $out = $unzipped
    } else { $out = $from }
    if (-not (Test-Path (Join-Path $out 'index.html'))) { throw "$out is not a static export (no index.html)" }
    node scripts/check-csp.mjs $out
    if ($LASTEXITCODE -ne 0) { throw 'inline <script> in the export would be blocked by the CSP' }
    if (Test-Path (Join-Path $out 'build-info.txt')) { "build: $(Get-Content (Join-Path $out 'build-info.txt'))" }
    $outs = aws cloudformation describe-stacks --stack-name codegen-frontend --query 'Stacks[0].Outputs' --output json @p | ConvertFrom-Json
    $bucket = ($outs | Where-Object OutputKey -eq 'BucketName').OutputValue
    $dist = ($outs | Where-Object OutputKey -eq 'DistributionId').OutputValue
    # hashed assets: cache for a year; HTML and replays: revalidate
    aws s3 sync "$out/_next" "s3://$bucket/_next" --cache-control 'public,max-age=31536000,immutable' --delete @s3 @p
    aws s3 sync $out "s3://$bucket" --exclude '_next/*' --exclude 'pyodide/*' --exclude '*.mjs' --exclude 'status.json' --exclude 'build-info.txt' --cache-control 'public,max-age=60' --delete @s3 @p
    # test bench: module scripts and wasm need exact types (the site sends nosniff); the runtime is version-pinned
    aws s3 cp "$out/testbench.worker.mjs" "s3://$bucket/testbench.worker.mjs" --content-type 'text/javascript' --cache-control 'public,max-age=60' @s3 @p
    aws s3 sync "$out/pyodide" "s3://$bucket/pyodide" --exclude '*' --include '*.mjs' --content-type 'text/javascript' --cache-control 'public,max-age=86400' --delete @s3 @p
    aws s3 sync "$out/pyodide" "s3://$bucket/pyodide" --exclude '*' --include '*.wasm' --content-type 'application/wasm' --cache-control 'public,max-age=86400' @s3 @p
    aws s3 sync "$out/pyodide" "s3://$bucket/pyodide" --exclude '*.mjs' --exclude '*.wasm' --cache-control 'public,max-age=86400' @s3 @p
    if ($DryRun) { 'dry run: nothing uploaded, no invalidation'; return }
    aws cloudfront create-invalidation --distribution-id $dist --paths '/*' --query 'Invalidation.Id' --output text @p
    "deployed: $(($outs | Where-Object OutputKey -eq 'SiteUrl').OutputValue)"
} finally {
    Pop-Location
    if ($unzipped) { Remove-Item -Recurse -Force $unzipped }
}
