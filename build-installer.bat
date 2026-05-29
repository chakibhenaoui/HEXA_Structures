@echo off
setlocal

cd /d "%~dp0"

echo ============================================
echo   HEXA Structures - Construction installateur
echo ============================================
echo.

if not exist "dist\HEXA Structures\HEXA Structures.exe" (
    echo ERREUR : executable PyInstaller introuvable.
    echo Lancez d'abord build.bat pour generer dist\HEXA Structures.
    exit /b 1
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo ERREUR : ISCC.exe introuvable.
    echo Installez Inno Setup 6 ou ajoutez ISCC.exe au PATH.
    exit /b 1
)

set "APP_VERSION=0.1.0"
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "$m = Select-String -Path 'config\settings.py' -Pattern '^APP_VERSION:\s*str\s*=\s*\x22([^\x22]+)\x22'; if ($m) { $m.Matches[0].Groups[1].Value }"`) do set "APP_VERSION=%%V"

if not exist "dist\installer" mkdir "dist\installer"

echo [1/1] Compilation Inno Setup...
echo       Version : %APP_VERSION%
echo       Compilateur : %ISCC%
echo.

"%ISCC%" /DAppVersion=%APP_VERSION% "installer\hexa_structures.iss"
if errorlevel 1 (
    echo.
    echo ERREUR : la compilation de l'installateur a echoue.
    exit /b 1
)

echo.
echo ============================================
echo   INSTALLATEUR CREE !
echo   Fichier : dist\installer\HEXA_Structures_Setup_%APP_VERSION%.exe
echo ============================================
