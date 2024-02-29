# Common functions for Windows packaging scripts

Param(
  [ValidateScript({ (Test-Path $_ -PathType Leaf) -or (-not $_) })]
  [String]
  $CertificateFile,
  [SecureString]
  $CertificatePassword
)

# RFC 3161 timestamp server for code signing
$TimeStampServer = 'http://ts.ssl.com'

Function CodeSignBinary {
  Param(
    [ValidateScript({Test-Path $_ -PathType Leaf})]
    [String]
    $BinaryPath
  )
  If ($CertificateFile) {
    SignTool sign /v /fd SHA256 /tr "$TimeStampServer" /td sha256 `
      /f "$CertificateFile" /p (ConvertFrom-SecureString -AsPlainText $CertificatePassword) `
      $BinaryPath
    ThrowOnExeError "SignTool failed"
  } Else {
    Write-Output "Skip signing $BinaryPath"
  }
}

Function ThrowOnExeError {
  Param( [String]$Message )
  If ($LastExitCode -ne 0) {
    Throw $Message
  }
}

Function FinalizePackage {
  Param(
    [ValidateScript({Test-Path $_ -PathType Container})]
    [String]
    $Path
  )

  CodeSignBinary -BinaryPath (Join-Path -Path $Path -ChildPath picard.exe) -ErrorAction Stop
  CodeSignBinary -BinaryPath (Join-Path -Path $Path -ChildPath fpcalc.exe) -ErrorAction Stop
  CodeSignBinary -BinaryPath (Join-Path -Path $Path -ChildPath discid.dll) -ErrorAction Stop

  # Move all Qt5 DLLs into the main folder to avoid conflicts with system wide
  # versions of those dependencies. Since some version PyInstaller tries to
  # maintain the file hierarchy of imported modules, but this easily breaks
  # DLL loading on Windows.
  # Workaround for https://tickets.metabrainz.org/browse/PICARD-2736
  $Qt5BinDir = (Join-Path -Path $Path -ChildPath PyQt5\Qt5\bin)
  Move-Item -Path (Join-Path -Path $Qt5BinDir -ChildPath *.dll) -Destination $Path -Force
  Remove-Item -Path $Qt5BinDir
}

Function DownloadFile {
  Param(
    [Parameter(Mandatory = $true)]
    [String]
    $FileName,
    [Parameter(Mandatory = $true)]
    [String]
    $Url
  )
  $OutputPath = (Join-Path (Resolve-Path .) $FileName)
  (New-Object System.Net.WebClient).DownloadFile($Url, "$OutputPath")
}

Function VerifyHash {
  Param(
    [Parameter(Mandatory = $true)]
    [String]
    $FileName,
    [Parameter(Mandatory = $true)]
    [String]
    $Sha256Sum
  )
  If ((Get-FileHash "$FileName").hash -ne "$Sha256Sum") {
    Throw "Invalid SHA256 hash for $FileName"
  }
}
