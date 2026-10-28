<#
Destroy the backend stack; keep everything else unless -All.

  .\teardown.ps1            deletes codegen-backend (Lambda, Function URL, alarm, SNS topic, breaker, log groups)
  .\teardown.ps1 -All       also deletes, in order:
                              codegen-frontend    the site bucket is emptied first (CloudFormation cannot delete a
                                                  non-empty bucket), then the bucket and the CloudFront distribution go
                                                  with the stack; disabling the distribution takes several minutes
                              codegen-ecr         image repo, emptied on delete
                              codegen-persistent  the stack only: the table has DeletionPolicy: Retain, so delete it with
                                                  aws dynamodb delete-table --table-name codegen-state
The SAM bootstrap stack (aws-sam-cli-managed-default, an artifacts bucket) costs nothing and is kept.
#>
param([switch]$All)
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$p = '--region', 'eu-north-1', '--profile', 'codegen-spike'
$common = $p + '--no-prompts'
sam delete --stack-name codegen-backend @common
if ($All) {
    $bucket = aws cloudformation describe-stacks --stack-name codegen-frontend --query "Stacks[0].Outputs[?OutputKey=='BucketName'].OutputValue" --output text @p 2>$null
    if ($LASTEXITCODE -eq 0 -and $bucket -and $bucket -ne 'None') { aws s3 rm "s3://$bucket" --recursive --only-show-errors @p }
    foreach ($s in 'codegen-frontend', 'codegen-ecr', 'codegen-persistent') { sam delete --stack-name $s @common }
}
