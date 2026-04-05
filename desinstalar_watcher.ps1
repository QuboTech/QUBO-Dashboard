# desinstalar_watcher.ps1
$NomeTarefa = "QUBO_FileWatcher"
Stop-ScheduledTask -TaskName $NomeTarefa -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "[OK] QUBO Watcher removido do Windows." -ForegroundColor Green
Read-Host "Pressione Enter para fechar"
