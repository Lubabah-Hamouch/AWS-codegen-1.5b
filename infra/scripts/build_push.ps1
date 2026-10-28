<#
Build the arm64 image with buildx and push it to ECR; prints the image URI (by digest) for `sam deploy`.

  .\build_push.ps1 -Dockerfile Dockerfile.spike -Tag spike-1

Why not `sam build`: its legacy builder resolves multi-arch base layers (the Web Adapter) to the host platform and fails
for arm64. buildx with --provenance=false also yields a single-manifest image, which Lambda requires.
#>
param([string]$Dockerfile = 'Dockerfile.spike', [Parameter(Mandatory)][string]$Tag)
$ErrorActionPreference = 'Stop'
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$p = '--profile', 'codegen-spike', '--region', 'eu-north-1'
$repo = aws ecr describe-repositories --repository-names codegen-backend --query 'repositories[0].repositoryUri' --output text @p
$registry = $repo.Split('/')[0]
aws ecr get-login-password @p | docker login --username AWS --password-stdin $registry | Out-Null
$ctx = Join-Path $PSScriptRoot '..\..\backend'
docker buildx build --platform linux/arm64 --provenance=false --sbom=false -f (Join-Path $ctx $Dockerfile) -t "${repo}:$Tag" --push $ctx
if ($LASTEXITCODE -ne 0) { throw 'build/push failed' }
$digest = aws ecr describe-images --repository-name codegen-backend --image-ids imageTag=$Tag --query 'imageDetails[0].imageDigest' --output text @p
"IMAGE_URI=${repo}@${digest}"
