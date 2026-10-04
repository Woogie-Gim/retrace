# PyInstaller 빌드 : 엔진(onedir) + 데모 쇼핑몰(onefile)
# 출력 : engine/dist/engine/engine.exe, demo-shop/dist/demo-shop.exe
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$pyinstaller = Join-Path $root 'engine\.venv\Scripts\pyinstaller.exe'

# 엔진 : Selenium Manager 바이너리·gherkin 데이터 포함
& $pyinstaller -n engine --onedir --noconfirm --clean `
  --collect-all selenium --collect-all gherkin --collect-submodules uvicorn `
  --paths "$root\engine" `
  --distpath "$root\engine\dist" --workpath "$root\engine\build" --specpath "$root\engine\build" `
  "$root\engine\engine_entry.py"
if ($LASTEXITCODE -ne 0) { throw "engine 빌드 실패 ($LASTEXITCODE)" }

# 데모 쇼핑몰 : 정적 화면 포함
& $pyinstaller -n demo-shop --onefile --noconfirm --clean `
  --add-data "$root\demo-shop\demo_shop\static;demo_shop\static" --collect-submodules uvicorn `
  --paths "$root\demo-shop" `
  --distpath "$root\demo-shop\dist" --workpath "$root\demo-shop\build" --specpath "$root\demo-shop\build" `
  "$root\demo-shop\demo_shop_entry.py"
if ($LASTEXITCODE -ne 0) { throw "demo-shop 빌드 실패 ($LASTEXITCODE)" }
