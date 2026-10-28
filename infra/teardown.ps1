<#
Destroy the backend stack(s); keep the persistent stack (DynamoDB table with its counters and keys) unless -All.

  .\teardown.ps1            deletes codegen-backend (Lambda, Function URL, log group)
  .\teardown.ps1 -All       also deletes the image repo (codegen-ecr, emptied on delete) and the persistent stack. The table
                            has DeletionPolicy: Retain, so it is kept even then; delete it with:
                            aws dynamodb delete-table --table-name codegen-state
The SAM bootstrap stack (aws-sam-cli-managed-default, an artifacts bucket) costs nothing and is kept.
#>
param([switch]$All)
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$common = '--region', 'eu-north-1', '--profile', 'codegen-spike', '--no-prompts'
foreach ($s in 'codegen-backend') { sam delete --stack-name $s @common }
if ($All) { foreach ($s in 'codegen-ecr', 'codegen-persistent') { sam delete --stack-name $s @common } }
