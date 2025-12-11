\
        if (-not (Test-Path .venv)) {
          Write-Host 'Run scripts\env_setup.ps1 first to create the venv.' -ForegroundColor Yellow
          exit 1
        }
        . .\.venv\Scripts\Activate.ps1
        python .\apps\gui\scholarone_gui_app.py
