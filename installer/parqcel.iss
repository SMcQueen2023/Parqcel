; Inno Setup script for the standalone Parqcel desktop build.
; Build the PyInstaller bundle first with scripts\build_windows_desktop.ps1.

[Setup]
AppName=Parqcel
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\Parqcel
UsePreviousAppDir=no
DefaultGroupName=Parqcel
OutputDir=dist
OutputBaseFilename=Parqcel-Installer
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
; Use path relative to this .iss file (installer/.. -> project root)
SetupIconFile={#SourcePath}\..\src\parqcel\assets\parqcel_icon.ico
UninstallDisplayIcon={app}\parqcel_icon.ico

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; Flags: unchecked

[Files]
; Copy the standalone desktop build into the install directory.
Source: "{#SourcePath}\..\dist\Parqcel\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs
; Also drop the icon at the app root for shortcut reliability
Source: "{#SourcePath}\..\src\parqcel\assets\parqcel_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Parqcel"; Filename: "{app}\Parqcel.exe"; WorkingDir: "{autodocs}"; IconFilename: "{app}\parqcel_icon.ico"
Name: "{autodesktop}\Parqcel"; Filename: "{app}\Parqcel.exe"; WorkingDir: "{autodocs}"; IconFilename: "{app}\parqcel_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Parqcel.exe"; Description: "Launch Parqcel"; Flags: nowait postinstall skipifsilent unchecked
