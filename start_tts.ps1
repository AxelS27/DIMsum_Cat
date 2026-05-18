$GPT_SOVITS_DIR = "D:\GPT-SoVITS"
$HOST_ADDR      = "127.0.0.1"
$PORT           = 9880

chcp 65001 | Out-Null
Write-Host "Starting GPT-SoVITS API server on http://${HOST_ADDR}:${PORT} ..."
Push-Location $GPT_SOVITS_DIR
& "$GPT_SOVITS_DIR\runtime\python.exe" "api_v2.py" -a $HOST_ADDR -p $PORT -c "GPT_SoVITS\configs\tts_infer.yaml"
Pop-Location
