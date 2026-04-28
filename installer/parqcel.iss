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
Name: "install_profile\base"; Description: "Base install (viewer/editor only)"; Flags: exclusive
Name: "install_profile\ml"; Description: "ML install (adds featurization and dimensionality reduction)"; Flags: exclusive unchecked
Name: "install_profile\ai"; Description: "AI install (adds ML plus OpenAI/local AI integrations)"; Flags: exclusive unchecked
Name: "desktopicon"; Description: "Create a &desktop icon"; Flags: unchecked

[Files]
; Copy project files into install dir. Adjust Source path if building from elsewhere.
Source: "{#SourcePath}\..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs; Excludes: ".git;.venv;__pycache__;*.pyc;*.pyo;dist;build;.mypy_cache;.ruff_cache;.pytest_cache;.tox"
; Also drop the icon at the app root for shortcut reliability
Source: "{#SourcePath}\..\src\parqcel\assets\parqcel_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Ensure pip is present/up-to-date
Filename: "{code:GetPythonExe}"; Parameters: "-m pip install --upgrade pip"; StatusMsg: "Updating pip..."; Flags: runhidden shellexec waituntilterminated
; Install the selected Parqcel profile
Filename: "{code:GetPythonExe}"; Parameters: "-m pip install {code:GetInstallTarget}"; WorkingDir: "{app}"; StatusMsg: "Installing Parqcel..."; Flags: runhidden shellexec waituntilterminated

[Icons]
Name: "{group}\Parqcel"; Filename: "{code:GetPythonExe}"; Parameters: "-m parqcel"; WorkingDir: "{userdocs}"; IconFilename: "{app}\parqcel_icon.ico"
Name: "{userdesktop}\Parqcel"; Filename: "{code:GetPythonExe}"; Parameters: "-m parqcel"; WorkingDir: "{userdocs}"; IconFilename: "{app}\parqcel_icon.ico"; Tasks: desktopicon

[Code]
function GetInstallTarget(Param: string): string;
begin
  if WizardIsTaskSelected('install_profile\ai') then
  begin
    Result := '.[ai]';
    exit;
  end;

  if WizardIsTaskSelected('install_profile\ml') then
  begin
    Result := '.[ml]';
    exit;
  end;

  Result := '.';
end;

function GetPythonExe(Param: string): string;
begin
  // Preferred per-user installs under LocalAppData
  if FileExists(ExpandConstant('{localappdata}\Programs\Python\Python313\python.exe')) then
  begin
    Result := ExpandConstant('{localappdata}\Programs\Python\Python313\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe')) then
  begin
    Result := ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{localappdata}\Programs\Python\Python311\python.exe')) then
  begin
    Result := ExpandConstant('{localappdata}\Programs\Python\Python311\python.exe');
    exit;
  end;

  // Fallback to common system locations
  if FileExists(ExpandConstant('{pf64}\Python313\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\Python313\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{pf64}\Python312\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\Python312\python.exe');
    exit;
  end;
  if FileExists(ExpandConstant('{pf64}\Python311\python.exe')) then
  begin
    Result := ExpandConstant('{pf64}\Python311\python.exe');
    exit;
  end;

  // Last resort: try the py launcher in System32, otherwise python.exe on PATH
  if FileExists(ExpandConstant('{sys}\py.exe')) then
  begin
    Result := 'py';
    exit;
  end;

  Result := 'python.exe';
end;
