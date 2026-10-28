<#
Destroy the backend stack(s); keep the persistent stack (DynamoDB table with its counters and keys) unless -All.

  .\teardown.ps1            deletes codegen-spike-backend (Lambda, Function URL, log group)
  .\teardown.ps1 -All       also deletes the persistent stack. The table has DeletionPolicy: Retain, so the table itself
                            is kept even then; delete it with: aws dynamodb delete-table --table-name codegen-state
Images pushed by `sam deploy` live in the SAM-managed ECR repo (stack aws-sam-cli-managed-default); `sam delete`
asks to remove them, and the bootstrap stack itself costs nothing and is kept.
#>
param([switch]$All)
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$common = '--region', 'eu-north-1', '--profile', 'codegen-spike', '--no-prompts'
foreach ($s in 'codegen-spike-backend') { sam delete --stack-name $s @common }
if ($All) { sam delete --stack-name codegen-persistent @common }
