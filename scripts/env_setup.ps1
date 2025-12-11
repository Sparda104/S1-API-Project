\
        Write-Host 'Creating venv and installing requirements...' -ForegroundColor Cyan
        python -m venv .venv
        . .\.venv\Scripts\Activate.ps1
        pip install --upgrade pip
        pip install -r requirements.txt
        Write-Host 'Done.' -ForegroundColor Green
