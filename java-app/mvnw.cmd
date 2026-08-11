@ECHO OFF
SETLOCAL
SET "PROJECT_BASE_DIR=%~dp0"
SET "PROJECT_BASE_DIR=%PROJECT_BASE_DIR:~0,-1%"
SET "WRAPPER_JAR=%PROJECT_BASE_DIR%\.mvn\wrapper\maven-wrapper.jar"

IF NOT EXIST "%WRAPPER_JAR%" (
  ECHO Maven wrapper JAR is missing: "%WRAPPER_JAR%" 1>&2
  EXIT /B 1
)

IF DEFINED JAVA_HOME (
  SET "JAVA_EXE=%JAVA_HOME%\bin\java.exe"
) ELSE (
  SET "JAVA_EXE=java.exe"
)

"%JAVA_EXE%" -classpath "%WRAPPER_JAR%" "-Dmaven.multiModuleProjectDirectory=%PROJECT_BASE_DIR%" org.apache.maven.wrapper.MavenWrapperMain %*
EXIT /B %ERRORLEVEL%
