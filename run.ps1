Write-Host "🚀 Launching Chat Unreal V2..."
Set-ExecutionPolicy Bypass -Scope Process -Force
cd "C:\Users\moe\Chat_Unreal_V2"
if (-not (Test-Path "venv")) { python -m venv venv }
.\venv\Scripts\Activate.ps1
pip install --upgrade pip flask requests beautifulsoup4
python .\Chat_Unreal_Server.py
