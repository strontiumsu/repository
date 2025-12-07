@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Usage: delete-by-substring.bat "C:\path\to\folder" "substring" [/dryrun]

if "%~2"=="" (
  echo Usage: %~nx0 "folder" "substring" [/dryrun]
  exit /b 1
)

set "ROOT=%~1"
set "SUB=%~2"
set "DRY="
if /I "%~3"=="/dryrun" set "DRY=1"

if not exist "%ROOT%" (
  echo [ERROR] Folder not found: "%ROOT%"
  exit /b 1
)

set "COUNT=0"

for /r "%ROOT%" %%F in (*) do (
  rem Match the substring literally in the FILE NAME (case-insensitive)
  rem Change %%~nxF to %%~fF if you want to match against the FULL PATH instead.
  echo(%%~nxF | findstr /I /L /C:"%SUB%" >nul
  if not errorlevel 1 (
    set /A COUNT+=1
    if defined DRY (
      echo [DRY-RUN] Would delete "%%~fF"
    ) else (
      del /F /Q "%%~fF" >nul 2>&1
      if errorlevel 1 (
        echo [FAILED] "%%~fF"
      ) else (
        echo [DELETED] "%%~fF"
      )
    )
  )
)

echo.
if defined DRY (
  echo [DRY-RUN] %COUNT% file^(s^) would be deleted.
) else (
  echo Done. %COUNT% file^(s^) processed.
)

exit /b
