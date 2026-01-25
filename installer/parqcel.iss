; Inno Setup script to install Parqcel using an existing Python
; Adjust Python path in GetPythonExe if your install differs.

[Setup]
AppName=Parqcel
AppVersion=0.1.0
DefaultDirName={userappdata}\Parqcel
DefaultGroupName=Parqcel
OutputDir=dist
OutputBaseFilename=Parqcel-Installer
Compression=lzma
SolidCompression=yes
; Use path relative to this .iss file (installer/.. -> project root)
SetupIconFile={#SourcePath}\..\src\parqcel\assets\parqcel_icon.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; Flags: unchecked

[Files]
; Copy project files into install dir. Adjust Source path if building from elsewhere.
Source: "{#SourcePath}\..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs; Excludes: ".git;.venv;__pycache__;*.pyc;*.pyo;dist;build;.mypy_cache;.ruff_cache;.pytest_cache;.tox"
; Also drop the icon at the app root for shortcut reliability
Source: "{#SourcePath}\..\src\parqcel\assets\parqcel_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Ensure pip is present/up-to-date
Filename: "{code:GetPythonExe}"; Parameters: "-m pip install --upgrade pip"; StatusMsg: "Updating pip..."; Flags: runhidden shellexec waituntilterminated
; Install Parqcel with AI extras; switch to .[ml] or bare . if you prefer
Filename: "{code:GetPythonExe}"; Parameters: "-m pip install .[ai]"; WorkingDir: "{app}"; StatusMsg: "Installing Parqcel..."; Flags: runhidden shellexec waituntilterminated

[Icons]
Name: "{group}\Parqcel"; Filename: "{code:GetPythonExe}"; Parameters: "-m parqcel"; WorkingDir: "{userdocs}"; IconFilename: "{app}\parqcel_icon.ico"
Name: "{userdesktop}\Parqcel"; Filename: "{code:GetPythonExe}"; Parameters: "-m parqcel"; WorkingDir: "{userdocs}"; IconFilename: "{app}\parqcel_icon.ico"; Tasks: desktopicon

[Code]
function GetPythonExe(Param: string): string;
begin
  // Preferred specific install (adjust if your Python path differs)
  if FileExists('C:\\Users\\scott\\AppData\\Local\\Programs\\Python\\Python313\\python.exe') then
  begin
    Result := 'C:\\Users\\scott\\AppData\\Local\\Programs\\Python\\Python313\\python.exe';
    exit;
  end;
  // Fallback to common locations
  if FileExists(ExpandConstant('{pf64}\\Python313\\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\\Python313\\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{pf64}\\Python312\\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\\Python312\\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{pf64}\\Python311\\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\\Python311\\python.exe');
    exit;
  end;
  // Last resort: try the py launcher in System32, otherwise python.exe on PATH
  if FileExists(ExpandConstant('{sys}\py.exe')) then
  begin
    Result := 'py'
    exit;
  end;
  Result := 'python.exe';
end;
