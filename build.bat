@echo off
echo ============================================
echo   HEXA Structures - Construction de l'executable
echo ============================================
echo.

REM Vérifier que le venv existe
if not exist ".venv\Scripts\python.exe" (
    echo ERREUR : Environnement virtuel non trouve.
    echo Executez d'abord : py -3.12 -m venv .venv
    echo Puis : .venv\Scripts\pip install -r requirements.txt pyinstaller
    pause
    exit /b 1
)

echo [1/3] Nettoyage des builds precedents...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

echo [2/3] Construction de l'executable avec PyInstaller...
echo      Cible supportee : Windows 10/11.
echo      Note : OpenSeesPy n'est PAS integre au build.
echo      HEXA Structures detecte une installation Python externe compatible.
.venv\Scripts\python.exe -m PyInstaller hexa_structures.spec --noconfirm

echo.
if exist "dist\HEXA Structures\HEXA Structures.exe" (
    echo [3/3] Signature numerique locale...
    powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\sign-windows.ps1"
    if errorlevel 1 (
        echo ERREUR : La signature numerique a echoue.
        pause
        exit /b 1
    )
    echo.
    echo ============================================
    echo   BUILD REUSSI !
    echo   Executable : dist\HEXA Structures\HEXA Structures.exe
    echo   Signature : certificat local auto-signe
    echo ============================================
) else (
    echo ERREUR : Le build a echoue.
    echo Verifiez les erreurs ci-dessus.
)

pause
