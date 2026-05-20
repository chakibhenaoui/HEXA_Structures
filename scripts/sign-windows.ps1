[CmdletBinding()]
param(
    [string]$FilePath = "",
    [string]$PfxPath = "",
    [string]$PasswordFile = "",
    [string]$Subject = "CN=HEXA Structures Local Test Code Signing",
    [string]$TimestampServer = "",
    [switch]$ForceNewCertificate
)

$ErrorActionPreference = "Stop"

$scriptDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($scriptDir)) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir ".."))

if ([string]::IsNullOrWhiteSpace($FilePath)) {
    $FilePath = Join-Path $repoRoot "dist\HEXA Structures\HEXA Structures.exe"
}
if ([string]::IsNullOrWhiteSpace($PfxPath)) {
    $PfxPath = Join-Path $repoRoot ".tmp\signing\hexa_structures_test_codesign.pfx"
}
if ([string]::IsNullOrWhiteSpace($PasswordFile)) {
    $PasswordFile = Join-Path $repoRoot ".tmp\signing\hexa_structures_test_codesign.password.txt"
}

function Resolve-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function New-RandomPassword {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    finally {
        $rng.Dispose()
    }
}

function Remove-CertificateFromCurrentUserStore {
    param([string]$Thumbprint)

    if ([string]::IsNullOrWhiteSpace($Thumbprint)) {
        return
    }

    $certPath = "Cert:\CurrentUser\My\$Thumbprint"
    if (Test-Path $certPath) {
        Remove-Item -Path $certPath -Force -ErrorAction SilentlyContinue
    }
}

$targetFile = Resolve-FullPath $FilePath
$pfxFile = Resolve-FullPath $PfxPath
$passwordPath = Resolve-FullPath $PasswordFile
$certificateFile = [System.IO.Path]::ChangeExtension($pfxFile, ".cer")

if (-not (Test-Path $targetFile)) {
    throw "Executable introuvable : $targetFile"
}

$signingDir = Split-Path -Parent $pfxFile
if (-not (Test-Path $signingDir)) {
    New-Item -ItemType Directory -Path $signingDir | Out-Null
}

if ($ForceNewCertificate -or -not (Test-Path $pfxFile) -or -not (Test-Path $passwordPath)) {
    if (Test-Path $pfxFile) {
        Remove-Item -Path $pfxFile -Force
    }
    if (Test-Path $passwordPath) {
        Remove-Item -Path $passwordPath -Force
    }
    if (Test-Path $certificateFile) {
        Remove-Item -Path $certificateFile -Force
    }

    $plainPassword = New-RandomPassword
    $securePassword = ConvertTo-SecureString $plainPassword -AsPlainText -Force

    $createdCertificate = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -KeyAlgorithm RSA `
        -KeyLength 3072 `
        -HashAlgorithm SHA256 `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(3)

    try {
        Export-PfxCertificate `
            -Cert $createdCertificate `
            -FilePath $pfxFile `
            -Password $securePassword | Out-Null
        Export-Certificate `
            -Cert $createdCertificate `
            -FilePath $certificateFile | Out-Null
        Set-Content -Path $passwordPath -Value $plainPassword -Encoding ASCII
    }
    finally {
        Remove-CertificateFromCurrentUserStore -Thumbprint $createdCertificate.Thumbprint
    }
}

$pfxPassword = Get-Content -Path $passwordPath -Raw
$pfxPassword = $pfxPassword.Trim()
$securePfxPassword = ConvertTo-SecureString $pfxPassword -AsPlainText -Force

$importedCertificate = Import-PfxCertificate `
    -FilePath $pfxFile `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -Password $securePfxPassword `
    -Exportable

try {
    $signParameters = @{
        FilePath = $targetFile
        Certificate = $importedCertificate
        HashAlgorithm = "SHA256"
    }

    if (-not [string]::IsNullOrWhiteSpace($TimestampServer)) {
        $signParameters.TimestampServer = $TimestampServer
    }

    $signature = Set-AuthenticodeSignature @signParameters
    $verification = Get-AuthenticodeSignature -FilePath $targetFile

    if ($verification.Status -eq "NotSigned") {
        throw "La signature a echoue : le fichier est encore indique comme non signe."
    }

    Write-Host "Executable signe : $targetFile"
    Write-Host "Certificat public : $certificateFile"
    Write-Host "Statut Authenticode : $($verification.Status)"
    Write-Host "Empreinte certificat : $($importedCertificate.Thumbprint)"

    if ($verification.Status -ne "Valid") {
        Write-Warning "Le statut peut rester non approuve avec un certificat auto-signe. Pour un editeur reconnu, utilisez un certificat de signature de code public."
    }
}
finally {
    Remove-CertificateFromCurrentUserStore -Thumbprint $importedCertificate.Thumbprint
}
