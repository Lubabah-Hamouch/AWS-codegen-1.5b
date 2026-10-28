<#
Emergency stop for the public Function URL. Two independent layers; `on` engages both.

  .\killswitch.ps1 on        1) DynamoDB flag: the app refuses every request (503)
                             2) Function URL auth -> AWS_IAM: AWS itself rejects unsigned requests (403) before
                                any code runs, so this works even if the app or the table is broken
  .\killswitch.ps1 off       reverses both
  .\killswitch.ps1 status    shows both

Layer 1 takes effect immediately. Layer 2 is eventually consistent: measured between ~3 s and over 60 s to
propagate in both directions, and the status can flap meanwhile. Verify with an unauthenticated GET of /health (403 = engaged).
Note: layer 2 changes a CloudFormation-managed setting; a later `sam deploy` resets it to what the template says (NONE).
#>
param([Parameter(Mandatory)][ValidateSet('on', 'off', 'status')][string]$Action,
      [string]$FunctionName = 'codegen-backend')
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
$p = '--profile', 'codegen-spike', '--region', 'eu-north-1'
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot 'seed_state.py'

# $ErrorActionPreference does not cover native commands: stop on any failed aws or python call, so a half-applied
# switch is reported as a failure instead of looking done.
function Invoke-Native {
    $exe, $rest = $args
    & $exe @rest
    if ($LASTEXITCODE -ne 0) { throw "$exe $($rest[0]) $($rest[1]) failed (exit $LASTEXITCODE)" }
}
function Get-Auth { Invoke-Native aws lambda get-function-url-config --function-name $FunctionName --query AuthType --output text @p }

switch ($Action) {
    'on' {
        # Order matters: cut access at AWS first, then set the app flag.
        Invoke-Native aws lambda update-function-url-config --function-name $FunctionName --auth-type AWS_IAM --query AuthType --output text @p
        Invoke-Native python $py --kill on
    }
    'off' {
        Invoke-Native python $py --kill off
        Invoke-Native aws lambda update-function-url-config --function-name $FunctionName --auth-type NONE --query AuthType --output text @p
    }
    'status' {
        "Function URL auth type: $(Get-Auth)"
        Invoke-Native python $py --show
    }
}
