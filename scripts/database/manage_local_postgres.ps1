param(
    [ValidateSet('inspect', 'start', 'stop')]
    [string]$Action = 'inspect'
)

# Controls only the dedicated project instance; no install, SQL or role changes.
& wsl.exe -d Ubuntu-E --user aipof-dbtest --exec `
    /mnt/e/Projeler/Ai_Proje_Ofisi/.runtime/kernel-linux314/bin/python -B `
    /mnt/e/Projeler/Ai_Proje_Ofisi/scripts/database/local_postgres.py $Action
exit $LASTEXITCODE
