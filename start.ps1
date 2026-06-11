if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    $secret = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
    (Get-Content .env) -replace 'change-this-to-a-long-random-string', $secret | Set-Content .env
    Write-Host "Created .env with a generated SECRET_KEY."
    Write-Host "Edit .env if you want to set a custom POSTGRES_PASSWORD before continuing."
    Write-Host ""
}

docker compose up --build @args