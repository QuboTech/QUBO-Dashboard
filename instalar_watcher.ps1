# instalar_watcher.ps1
# Registra o file_watcher.py para iniciar automaticamente com o Windows
# Execute como Administrador

$NomeTarefa = "QUBO_FileWatcher"
$PastaQubo  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python     = (Get-Command python -ErrorAction SilentlyContinue).Source
$Watcher    = Join-Path $PastaQubo "file_watcher.py"
$LogFile    = Join-Path $PastaQubo "data\watcher.log"

if (-not $Python) {
    Write-Host "[ERRO] Python nao encontrado. Instale o Python e tente novamente." -ForegroundColor Red
    Read-Host; exit 1
}

if (-not (Test-Path $Watcher)) {
    Write-Host "[ERRO] file_watcher.py nao encontrado em $PastaQubo" -ForegroundColor Red
    Read-Host; exit 1
}

# Remove tarefa existente se houver
Unregister-ScheduledTask -TaskName $NomeTarefa -Confirm:$false -ErrorAction SilentlyContinue

# Cria a acao: roda python file_watcher.py --watch com log
$Acao = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "`"$Watcher`" --watch" `
    -WorkingDirectory $PastaQubo

# Gatilho: iniciar ao fazer login do usuario
$Gatilho = New-ScheduledTaskTrigger -AtLogOn

# Configuracoes: rodar em background, reiniciar se falhar
$Configuracao = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RunOnlyIfNetworkAvailable `
    -StartWhenAvailable

# Registra a tarefa
Register-ScheduledTask `
    -TaskName $NomeTarefa `
    -Action $Acao `
    -Trigger $Gatilho `
    -Settings $Configuracao `
    -Description "QUBO: monitora pasta de PDFs e envia para Supabase automaticamente" `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "  QUBO Watcher instalado como tarefa do Windows!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Tarefa: $NomeTarefa" -ForegroundColor Cyan
Write-Host "  Inicia: automaticamente ao fazer login" -ForegroundColor Cyan
Write-Host "  Python: $Python" -ForegroundColor Cyan
Write-Host "  Script: $Watcher" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Para verificar: Agendador de Tarefas -> $NomeTarefa" -ForegroundColor Yellow
Write-Host "  Para parar:     .\desinstalar_watcher.ps1" -ForegroundColor Yellow
Write-Host ""

# Pergunta se quer iniciar agora
$resp = Read-Host "Deseja iniciar o watcher AGORA? (s/n)"
if ($resp -eq "s" -or $resp -eq "S") {
    Start-ScheduledTask -TaskName $NomeTarefa
    Write-Host "[OK] Watcher iniciado! Monitorando pasta de PDFs..." -ForegroundColor Green
}
Read-Host "Pressione Enter para fechar"
