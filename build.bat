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

echo [1/4] Nettoyage des builds precedents...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

echo [2/4] Construction de l'executable avec PyInstaller...
echo      Cible supportee : Windows 10/11.
echo      Note : OpenSeesPy n'est PAS integre au build.
echo      Note : les catalogues i18n sont integres dans la build.
echo      HEXA Structures detecte une installation Python externe compatible.
.venv\Scripts\python.exe -m PyInstaller hexa_structures.spec --noconfirm

echo.
if exist "dist\HEXA Structures\HEXA Structures.exe" (
    set "EXE_PATH=dist\HEXA Structures\HEXA Structures.exe"
    set "I18N_DIR=dist\HEXA Structures\_internal\i18n"
    set "SMOKE_DIR=dist\smoke-tests"

    echo [3/4] Verification build et i18n...
    if not exist "%I18N_DIR%\hexa_fr.qm" (
        echo ERREUR : catalogue francais manquant dans %I18N_DIR%.
        pause
        exit /b 1
    )
    if not exist "%I18N_DIR%\hexa_en.qm" (
        echo ERREUR : catalogue anglais manquant dans %I18N_DIR%.
        pause
        exit /b 1
    )
    if not exist "%SMOKE_DIR%" mkdir "%SMOKE_DIR%"
    set "QT_QPA_PLATFORM=offscreen"

    echo      Smoke test langue anglaise...
    start "" /wait "%EXE_PATH%" --smoke-test --smoke-language en --smoke-output "%SMOKE_DIR%\language-en.json"
    if errorlevel 1 (
        echo ERREUR : le smoke test anglais a echoue.
        pause
        exit /b 1
    )
    if not exist "%SMOKE_DIR%\language-en.json" (
        echo ERREUR : rapport smoke test anglais introuvable.
        pause
        exit /b 1
    )

    echo      Smoke test avec catalogue anglais manquant...
    ren "%I18N_DIR%\hexa_en.qm" "hexa_en.qm.bak"
    start "" /wait "%EXE_PATH%" --smoke-test --smoke-language en --smoke-allow-language-fallback --smoke-output "%SMOKE_DIR%\missing-en-qm.json"
    set "SMOKE_MISSING_STATUS=%ERRORLEVEL%"
    ren "%I18N_DIR%\hexa_en.qm.bak" "hexa_en.qm"
    if not "%SMOKE_MISSING_STATUS%"=="0" (
        echo ERREUR : le demarrage avec catalogue anglais manquant a echoue.
        pause
        exit /b 1
    )
    if not exist "%SMOKE_DIR%\missing-en-qm.json" (
        echo ERREUR : rapport smoke test catalogue manquant introuvable.
        pause
        exit /b 1
    )

    echo [4/4] Signature numerique locale...
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
    echo   i18n : dist\HEXA Structures\_internal\i18n
    echo   Smoke tests : dist\smoke-tests
    echo   Signature : certificat local auto-signe
    echo ============================================
) else (
    echo ERREUR : Le build a echoue.
    echo Verifiez les erreurs ci-dessus.
)

pause
