py $PSScriptRoot\cli.py $args

$__CD_FILE = "__cd"
if (Test-Path $__CD_FILE) {
    $__CD_PATH = Get-Content $__CD_FILE
    Remove-Item $__CD_FILE
    Set-Location $__CD_PATH
}

$__RM_FILE = "__rm"
if (Test-Path $__RM_FILE) {
    $__RM_PATH = Get-Content $__RM_FILE
    Remove-Item $__RM_FILE
    Remove-Item -Recurse $__RM_PATH
}
