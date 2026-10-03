# Copyright 2026 RioPlay
# SPDX-License-Identifier: MIT
$ErrorActionPreference="Stop"
$py=Get-Command python -ErrorAction SilentlyContinue
if(-not $py){$py=Get-Command py -ErrorAction SilentlyContinue}
if(-not $py){throw "Python 3 is required."}
& $py.Source "$PSScriptRoot\bootstrap.py"
