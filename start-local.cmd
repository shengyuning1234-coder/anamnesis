@echo off
setlocal
set "ANAMNESIS_DOCKER=C:\Program Files\Docker\Docker\resources\bin\docker.exe"
if not exist "%ANAMNESIS_DOCKER%" set "ANAMNESIS_DOCKER=docker"
pushd "%~dp0"
"%ANAMNESIS_DOCKER%" info --format "{{.OSType}}"
if errorlevel 1 goto failed
"%ANAMNESIS_DOCKER%" compose -f compose.local.yaml build
if errorlevel 1 goto failed
"%ANAMNESIS_DOCKER%" compose -f compose.local.yaml up -d --no-build
if errorlevel 1 goto failed
echo Integrated word platform + OpenWebUI: http://127.0.0.1:5050/words/
echo The first OpenWebUI startup may take a few minutes.
popd
exit /b 0
:failed
echo Startup failed. Check Docker Desktop and port 5050.
popd
exit /b 1
