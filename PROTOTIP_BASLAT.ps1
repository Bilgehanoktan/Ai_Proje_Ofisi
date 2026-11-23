param([switch]$NoBrowser, [int]$Port = 8766)
# Görev ekranı varsayılan olarak gerçek backend olmadan açılır.
& 'C:\Python314\python.exe' -B (Join-Path $PSScriptRoot 'scripts/development/run.py') tasks --port $Port
exit $LASTEXITCODE
