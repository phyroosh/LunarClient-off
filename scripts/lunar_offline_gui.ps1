<#
.SYNOPSIS
    Lunar Client Offline Manager - Windows GUI & Patcher
.DESCRIPTION
    Zero-dependency native PowerShell GUI and management tool for Lunar Client on Windows.
    Enables offline account management with Mojang skin resolution, offline authentication
    patching for app.asar, and one-click launch.
#>

[CmdletBinding()]
param(
    [string]$Command = "gui",
    [string]$Username = "",
    [string]$Skin = "",
    [string]$Target = ""
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Web

# ==============================================================================
# Path Resolution
# ==============================================================================

$AccountsDir = Join-Path $env:USERPROFILE ".lunarclient\settings\game"
$AccountsFile = Join-Path $AccountsDir "accounts.json"
$SavedSkinsFile = Join-Path $AccountsDir "saved_skins.json"

function Get-AsarCandidates {
    return @(
        (Join-Path $env:LOCALAPPDATA "Programs\lunarclient\resources\app.asar"),
        (Join-Path $env:LOCALAPPDATA "Programs\Lunar Client\resources\app.asar"),
        (Join-Path $env:ProgramFiles "Lunar Client\resources\app.asar"),
        (Join-Path ${env:ProgramFiles(x86)} "Lunar Client\resources\app.asar"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\lunarclient\resources\app.asar"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\Lunar Client\resources\app.asar")
    )
}

function Find-LunarAsar([string]$customPath = "") {
    if ($customPath -and (Test-Path -Path $customPath -PathType Leaf)) {
        if ($customPath.ToLower().EndsWith(".asar")) { return $customPath }
        if ($customPath.ToLower().EndsWith(".exe")) {
            $dir = Split-Path -Parent $customPath
            $possible = Join-Path $dir "resources\app.asar"
            if (Test-Path $possible) { return $possible }
        }
        return $customPath
    }

    foreach ($c in (Get-AsarCandidates)) {
        if (Test-Path $c) { return $c }
    }

    # Search in Local Programs
    $localPrograms = Join-Path $env:LOCALAPPDATA "Programs"
    if (Test-Path $localPrograms) {
        $found = Get-ChildItem -Path $localPrograms -Filter "app.asar" -Recurse -ErrorAction SilentlyContinue |
                 Where-Object { $_.FullName -match "lunar" } | Select-Object -First 1
        if ($found) { return $found.FullName }
    }

    return (Get-AsarCandidates)[0]
}

function Find-LunarLauncher([string]$customPath = "") {
    if ($customPath -and (Test-Path -Path $customPath -PathType Leaf)) {
        if ($customPath.ToLower().EndsWith(".exe")) { return $customPath }
        if ($customPath.ToLower().EndsWith(".asar")) {
            $parent = Split-Path -Parent (Split-Path -Parent $customPath)
            $possible = Join-Path $parent "Lunar Client.exe"
            if (Test-Path $possible) { return $possible }
        }
        return $customPath
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\lunarclient\Lunar Client.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Lunar Client\Lunar Client.exe"),
        (Join-Path $env:ProgramFiles "Lunar Client\Lunar Client.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Lunar Client\Lunar Client.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\lunarclient\Lunar Client.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Programs\Lunar Client\Lunar Client.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    return $candidates[0]
}

# ==============================================================================
# Account Management Logic
# ==============================================================================

function Get-OfflineUUID([string]$name) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes("OfflinePlayer:$name")
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $hash = $md5.ComputeHash($bytes)
    # Version 3
    $hash[6] = ($hash[6] -band 0x0F) -bor 0x30
    # Variant RFC 4122
    $hash[8] = ($hash[8] -band 0x3F) -bor 0x80
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
}

function Get-ValidExpiry {
    # 7 days in future UTC
    $future = [DateTime]::UtcNow.AddDays(7)
    return $future.ToString("yyyy-MM-ddTHH:mm:ss.000Z")
}

function Resolve-Skin([string]$skinName) {
    $skinName = $skinName.Trim()
    if ([string]::IsNullOrWhiteSpace($skinName)) {
        return @{ UUID = $null; TextureUrl = $null; Model = "classic" }
    }

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $profileUrl = "https://api.mojang.com/users/profiles/minecraft/$skinName"
        $profile = Invoke-RestMethod -Uri $profileUrl -Method Get -TimeoutSec 5 -ErrorAction Stop

        if ($profile -and $profile.id) {
            $uuid = $profile.id
            $sessionUrl = "https://sessionserver.mojang.com/session/minecraft/profile/$uuid"
            $session = Invoke-RestMethod -Uri $sessionUrl -Method Get -TimeoutSec 5 -ErrorAction Stop

            if ($session -and $session.properties) {
                foreach ($prop in $session.properties) {
                    if ($prop.name -eq "textures") {
                        $rawJson = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($prop.value))
                        $texData = $rawJson | ConvertFrom-Json
                        $texUrl = $texData.textures.SKIN.url
                        $model = "classic"
                        if ($texData.textures.SKIN.metadata -and $texData.textures.SKIN.metadata.model) {
                            $model = $texData.textures.SKIN.metadata.model
                        }
                        return @{ UUID = $uuid; TextureUrl = $texUrl; Model = $model }
                    }
                }
            }
            return @{ UUID = $uuid; TextureUrl = $null; Model = "classic" }
        }
    } catch {
        # Fallback to offline UUID
    }

    return @{ UUID = (Get-OfflineUUID $skinName); TextureUrl = $null; Model = "classic" }
}

function Load-Accounts([bool]$autoRefresh = $true) {
    if (-not (Test-Path $AccountsFile)) {
        return @{ activeAccountLocalId = $null; accounts = @{} }
    }
    try {
        $content = Get-Content -Path $AccountsFile -Raw -Encoding UTF8
        $data = $content | ConvertFrom-Json -AsHashtable
        if ($null -eq $data.accounts) { $data.accounts = @{} }
        if ($autoRefresh) {
            Refresh-OfflineAccounts $data -SaveIfModified $true | Out-Null
        }
        return $data
    } catch {
        return @{ activeAccountLocalId = $null; accounts = @{} }
    }
}

function Save-Accounts($data) {
    if (-not (Test-Path $AccountsDir)) {
        New-Item -ItemType Directory -Path $AccountsDir -Force | Out-Null
    }
    $json = $data | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($AccountsFile, $json, [System.Text.Encoding]::UTF8)
}

function Refresh-OfflineAccounts($data = $null, [bool]$SaveIfModified = $true) {
    $saveNeeded = $false
    if ($null -eq $data) {
        $data = Load-Accounts -autoRefresh $false
        $saveNeeded = $true
    }

    if ($null -eq $data.accounts) { $data.accounts = @{} }
    $newExpiry = Get-ValidExpiry

    foreach ($lid in @($data.accounts.Keys)) {
        $acc = $data.accounts[$lid]
        $isOffline = ($lid -like "offline_*") -or
                     ($acc.accessToken -and $acc.accessToken.StartsWith("offline")) -or
                     ($acc.refreshToken -and $acc.refreshToken.StartsWith("offline"))

        if ($isOffline) {
            if (-not $acc.refreshToken) {
                $acc.refreshToken = "offline_refresh_$lid"
                $saveNeeded = $true
            }
            if (-not $acc.accessToken) {
                $acc.accessToken = "offline_token_$lid"
                $saveNeeded = $true
            }
            if ($acc.accessTokenExpiresAt -ne $newExpiry) {
                $acc.accessTokenExpiresAt = $newExpiry
                $saveNeeded = $true
            }
            if ($acc.type -ne "Xbox") {
                $acc.type = "Xbox"
                $saveNeeded = $true
            }
        }
    }

    if ($saveNeeded -and $SaveIfModified) {
        Save-Accounts $data
    }
    return $data
}

function Add-OfflineAccount([string]$user, [string]$skinName = "") {
    $user = $user.Trim()
    if ([string]::IsNullOrWhiteSpace($user)) {
        throw "Username cannot be empty."
    }

    $targetSkin = if ([string]::IsNullOrWhiteSpace($skinName)) { $user } else { $skinName.Trim() }
    $skinRes = Resolve-Skin $targetSkin
    $uuid = if ($skinRes.UUID) { $skinRes.UUID } else { Get-OfflineUUID $user }

    # Generate localId: offline_ + first 12 hex chars of sha256(user)
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $hashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($user))
    $hashHex = ($hashBytes | ForEach-Object { $_.ToString("x2") }) -join ""
    $localId = "offline_" + $hashHex.Substring(0, 12)

    $entry = @{
        accessToken          = "offline_token_$localId"
        accessTokenExpiresAt = Get-ValidExpiry
        localId              = $localId
        minecraftProfile     = @{
            id   = $uuid
            name = $user
        }
        refreshToken         = "offline_refresh_$localId"
        remoteId             = "remote_$localId"
        type                 = "Xbox"
        username             = $user
        eligibleForMigration = $false
        hasMultipleProfiles  = $false
        legacy               = $false
        persistent           = $true
        userProperties       = @()
    }

    $data = Load-Accounts -autoRefresh $false
    if ($null -eq $data.accounts) { $data.accounts = @{} }
    $data.accounts[$localId] = $entry
    $data.activeAccountLocalId = $localId
    Save-Accounts $data

    if ($skinRes.TextureUrl) {
        try {
            $savedSkins = @{}
            if (Test-Path $SavedSkinsFile) {
                $savedSkins = (Get-Content -Path $SavedSkinsFile -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable)
            }
            $savedSkins[$skinRes.TextureUrl] = @{
                type = if ($skinRes.Model -in @("classic", "slim")) { $skinRes.Model } else { "classic" }
                name = $targetSkin
            }
            $skinJson = $savedSkins | ConvertTo-Json -Depth 5
            [System.IO.File]::WriteAllText($SavedSkinsFile, $skinJson, [System.Text.Encoding]::UTF8)
        } catch { }
    }

    return $entry
}

function Set-ActiveAccount([string]$accIdentifier) {
    $data = Load-Accounts -autoRefresh $false
    $accounts = $data.accounts
    $targetId = $null

    if ($accounts.ContainsKey($accIdentifier)) {
        $targetId = $accIdentifier
    } else {
        foreach ($lid in $accounts.Keys) {
            if ($accounts[$lid].username -eq $accIdentifier) {
                $targetId = $lid
                break
            }
        }
    }

    if (-not $targetId) {
        throw "Account '$accIdentifier' not found."
    }

    $data.activeAccountLocalId = $targetId
    Save-Accounts $data
    return $accounts[$targetId]
}

function Remove-Account([string]$accIdentifier) {
    $data = Load-Accounts -autoRefresh $false
    $accounts = $data.accounts
    $targetId = $null

    if ($accounts.ContainsKey($accIdentifier)) {
        $targetId = $accIdentifier
    } else {
        foreach ($lid in $accounts.Keys) {
            if ($accounts[$lid].username -eq $accIdentifier) {
                $targetId = $lid
                break
            }
        }
    }

    if (-not $targetId) {
        throw "Account '$accIdentifier' not found."
    }

    $deletedUser = $accounts[$targetId].username
    $accounts.Remove($targetId)

    if ($data.activeAccountLocalId -eq $targetId) {
        $remaining = @($accounts.Keys)
        $data.activeAccountLocalId = if ($remaining.Count -gt 0) { $remaining[0] } else { $null }
    }

    Save-Accounts $data
    return $deletedUser
}

function Remove-AllAccounts {
    $data = Load-Accounts -autoRefresh $false
    $data.accounts = @{}
    $data.activeAccountLocalId = $null
    Save-Accounts $data
}

# ==============================================================================
# ASAR Patching Logic
# ==============================================================================

function Patch-MainJsCode([string]$code) {
    $t1 = "invalid:!e.refreshToken"
    $r1 = "invalid:!e.refreshToken&&!e.accessToken?.startsWith(`offline`)"
    if ($code.Contains($t1) -and -not $code.Contains($r1)) {
        $code = $code.Replace($t1, $r1)
    }

    $t2 = "try{nV.info(`Validating account ${r.minecraftProfile.name} owns Minecraft...`);"
    $r2 = "if(r.accessToken?.startsWith(`offline`)){nV.info(`[Offline] Account ${r.minecraftProfile.name} authenticated in offline mode.`);Ea(`account.guest`,!1);Z.store.dispatch(fK({uuid:r.minecraftProfile.id,loading:!1}));return;}try{nV.info(`Validating account ${r.minecraftProfile.name} owns Minecraft...`);"
    if ($code.Contains($t2) -and -not $code.Contains("[Offline] Account")) {
        $code = $code.Replace($t2, $r2)
    }

    $t3 = "XV=async(e,t)=>{if(!e)throw new zB(WB.NO_ACCOUNT,`No account found for getting Lunar Client Token`);"
    $r3 = "XV=async(e,t)=>{if(!e)throw new zB(WB.NO_ACCOUNT,`No account found for getting Lunar Client Token`);if(e.accessToken?.startsWith(`offline`))return`offline-jwt`;"
    if ($code.Contains($t3) -and -not $code.Contains("offline-jwt")) {
        $code = $code.Replace($t3, $r3)
    }

    $t4 = "async refreshAccountInternal(e){if(!e.refreshToken)throw new zB(WB.INVALID_SESSION,"
    $r4 = "async refreshAccountInternal(e){if(e.accessToken?.startsWith(`offline`)){nV.info(`[Offline] Account ${e.minecraftProfile?.name} refreshed locally.`);e.accessTokenExpiresAt=new Date(Date.now()+7*864e5).toISOString();let i=await pV();if(i.accounts[e.localId]){i.accounts[e.localId].accessTokenExpiresAt=e.accessTokenExpiresAt;await mV(i);}return e;}if(!e.refreshToken)throw new zB(WB.INVALID_SESSION,"
    if ($code.Contains($t4) -and -not $code.Contains("refreshed locally")) {
        $code = $code.Replace($t4, $r4)
    }

    return $code
}

function Patch-WindowsAsarDirect([string]$asarPath, [scriptblock]$logCallback) {
    function Log([string]$msg) {
        if ($logCallback) { & $logCallback $msg }
        else { Write-Host $msg }
    }

    if (-not (Test-Path $asarPath)) {
        throw "app.asar not found at: $asarPath"
    }

    $backupPath = "$asarPath.bak"
    if (-not (Test-Path $backupPath)) {
        Log "[*] Creating backup at: $(Split-Path -Leaf $backupPath)..."
        Copy-Item -Path $asarPath -Destination $backupPath -Force
    }

    Log "[1/3] Reading app.asar..."
    $fs = [System.IO.File]::Open($asarPath, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
    $br = New-Object System.IO.BinaryReader($fs)

    $magic = $br.ReadUInt32()
    $s1 = $br.ReadUInt32()
    $s2 = $br.ReadUInt32()
    $jsonLen = $br.ReadUInt32()

    $jsonBytes = $br.ReadBytes($jsonLen)
    $jsonStr = [System.Text.Encoding]::UTF8.GetString($jsonBytes)
    $header = $jsonStr | ConvertFrom-Json -AsHashtable
    $payloadBase = $fs.Position

    # Find main.js
    $targetRel = "dist-electron/electron/main.js"
    $node = $header.files["dist-electron"].files["electron"].files["main.js"]
    if (-not $node) {
        $fs.Close()
        throw "Could not locate dist-electron/electron/main.js in ASAR archive."
    }

    $offset = [int64]$node.offset
    $size = [int32]$node.size

    $fs.Seek($payloadBase + $offset, [System.IO.SeekOrigin]::Begin) | Out-Null
    $mainBytes = $br.ReadBytes($size)
    $mainCode = [System.Text.Encoding]::UTF8.GetString($mainBytes)

    if ($mainCode.Contains("[Offline] Account") -and $mainCode.Contains("refreshed locally")) {
        $fs.Close()
        Log "[i] Lunar Client is already patched for offline play!"
        return $true
    }

    Log "[2/3] Applying offline patch to main.js..."
    $patchedCode = Patch-MainJsCode $mainCode
    $patchedBytes = [System.Text.Encoding]::UTF8.GetBytes($patchedCode)

    Log "[3/3] Writing updated app.asar..."
    # Gather all file entries ordered by offset
    $entries = [System.Collections.Generic.List[psobject]]::new()
    function TraverseTree($tree, [string]$prefix = "") {
        foreach ($name in $tree.files.Keys) {
            $info = $tree.files[$name]
            $rel = if ($prefix) { "$prefix/$name" } else { $name }
            if ($info.files) {
                TraverseTree $info $rel
            } elseif (-not $info.unpacked) {
                $entries.Add([pscustomobject]@{
                    Rel    = $rel
                    Node   = $info
                    Offset = [int64]$info.offset
                    Size   = [int32]$info.size
                })
            }
        }
    }
    TraverseTree $header ""
    $sortedEntries = $entries | Sort-Object Offset

    $tempAsar = "$asarPath.tmp"
    $outFs = [System.IO.File]::Open($tempAsar, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $bw = New-Object System.IO.BinaryWriter($outFs)

    # First calculate new header JSON by updating offsets
    $curOffset = [int64]0
    foreach ($entry in $sortedEntries) {
        $curSize = if ($entry.Rel -eq $targetRel) { [int32]$patchedBytes.Length } else { $entry.Size }
        $entry.Node["offset"] = $curOffset.ToString()
        $entry.Node["size"] = $curSize
        $curOffset += $curSize
    }

    $newJsonStr = $header | ConvertTo-Json -Depth 20 -Compress
    $newJsonBytes = [System.Text.Encoding]::UTF8.GetBytes($newJsonStr)
    $pad = (4 - ($newJsonBytes.Length % 4)) % 4
    if ($pad -gt 0 -and $pad -lt 4) {
        $newJsonBytes = $newJsonBytes + ([System.Text.Encoding]::UTF8.GetBytes(" " * $pad))
    }
    $newJsonLen = [uint32]$newJsonBytes.Length

    # Write 16-byte pickle header
    $bw.Write([uint32]4)
    $bw.Write([uint32]($newJsonLen + 8))
    $bw.Write([uint32]($newJsonLen + 4))
    $bw.Write($newJsonLen)
    $bw.Write($newJsonBytes)

    # Copy files
    $buffer = New-Object byte[] 65536
    foreach ($entry in $sortedEntries) {
        if ($entry.Rel -eq $targetRel) {
            $bw.Write($patchedBytes)
        } else {
            $fs.Seek($payloadBase + $entry.Offset, [System.IO.SeekOrigin]::Begin) | Out-Null
            $remaining = $entry.Size
            while ($remaining -gt 0) {
                $toRead = [Math]::Min($remaining, $buffer.Length)
                $read = $fs.Read($buffer, 0, $toRead)
                if ($read -le 0) { break }
                $bw.Write($buffer, 0, $read)
                $remaining -= $read
            }
        }
    }

    $fs.Close()
    $outFs.Close()

    # Atomically replace
    Move-Item -Path $tempAsar -Destination $asarPath -Force
    Log "[✓] Successfully patched Lunar Client app.asar!"
    return $true
}

function Patch-LunarTarget([string]$targetPath = "", [scriptblock]$logCallback = $null) {
    $asar = Find-LunarAsar $targetPath

    # Check if Python script is present and python is in PATH
    $pyScript = Join-Path $PSScriptRoot "..\lunar_offline_manager.py"
    if (Test-Path $pyScript) {
        $pyExe = (Get-Command python.exe -ErrorAction SilentlyContinue)
        if ($pyExe) {
            if ($logCallback) { & $logCallback "[*] Using Python engine for patching..." }
            $res = & python.exe (Resolve-Path $pyScript).Path patch --target "$asar" 2>&1
            foreach ($line in $res) {
                if ($logCallback) { & $logCallback $line } else { Write-Host $line }
            }
            return $true
        }
    }

    # Fallback to pure PowerShell ASAR patcher
    return Patch-WindowsAsarDirect $asar $logCallback
}

function Launch-LunarClient([string]$customPath = "") {
    Refresh-OfflineAccounts -SaveIfModified $true | Out-Null
    $launcher = Find-LunarLauncher $customPath
    if (-not (Test-Path $launcher)) {
        throw "Lunar Client executable not found at: $launcher"
    }
    Start-Process -FilePath $launcher
}

# ==============================================================================
# GUI Implementation (Windows Forms Dark Theme)
# ==============================================================================

function Show-GUI {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Lunar Client Offline Manager (Windows Edition)"
    $form.Size = New-Object System.Drawing.Size(680, 560)
    $form.MinimumSize = New-Object System.Drawing.Size(640, 520)
    $form.StartPosition = "CenterScreen"

    # Breeze Dark Color Palette
    $BG_DARK     = [System.Drawing.ColorTranslator]::FromHtml("#232629")
    $BG_CARD     = [System.Drawing.ColorTranslator]::FromHtml("#31363b")
    $BG_INPUT    = [System.Drawing.ColorTranslator]::FromHtml("#1b1e20")
    $FG_TEXT     = [System.Drawing.ColorTranslator]::FromHtml("#eff0f1")
    $FG_MUTED    = [System.Drawing.ColorTranslator]::FromHtml("#bdc3c7")
    $ACCENT_GREEN = [System.Drawing.ColorTranslator]::FromHtml("#27ae60")
    $ACCENT_BLUE  = [System.Drawing.ColorTranslator]::FromHtml("#3daee9")
    $ACCENT_RED   = [System.Drawing.ColorTranslator]::FromHtml("#da4453")

    $form.BackColor = $BG_DARK
    $form.ForeColor = $FG_TEXT
    $form.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)

    # Header Panel
    $headerPanel = New-Object System.Windows.Forms.Panel
    $headerPanel.Dock = "Top"
    $headerPanel.Height = 55
    $headerPanel.BackColor = $BG_DARK
    $form.Controls.Add($headerPanel)

    $lblTitle = New-Object System.Windows.Forms.Label
    $lblTitle.Text = "🌙 Lunar Client Offline Manager"
    $lblTitle.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
    $lblTitle.AutoSize = $true
    $lblTitle.Location = New-Object System.Drawing.Point(18, 14)
    $headerPanel.Controls.Add($lblTitle)

    $lblSub = New-Object System.Windows.Forms.Label
    $lblSub.Text = "Windows Edition"
    $lblSub.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Italic)
    $lblSub.ForeColor = $ACCENT_BLUE
    $lblSub.AutoSize = $true
    $lblSub.Location = New-Object System.Drawing.Point(340, 18)
    $headerPanel.Controls.Add($lblSub)

    # Bottom Panel (Status & Launch)
    $bottomPanel = New-Object System.Windows.Forms.Panel
    $bottomPanel.Dock = "Bottom"
    $bottomPanel.Height = 60
    $bottomPanel.BackColor = $BG_DARK
    $form.Controls.Add($bottomPanel)

    $lblStatus = New-Object System.Windows.Forms.Label
    $lblStatus.Text = "Ready"
    $lblStatus.ForeColor = $FG_MUTED
    $lblStatus.AutoSize = $true
    $lblStatus.Location = New-Object System.Drawing.Point(20, 20)
    $bottomPanel.Controls.Add($lblStatus)

    $btnLaunch = New-Object System.Windows.Forms.Button
    $btnLaunch.Text = "🚀 Launch Lunar Client"
    $btnLaunch.Size = New-Object System.Drawing.Size(185, 38)
    $btnLaunch.Location = New-Object System.Drawing.Point(465, 11)
    $btnLaunch.Anchor = "Top,Right"
    $btnLaunch.BackColor = $ACCENT_BLUE
    $btnLaunch.ForeColor = [System.Drawing.Color]::White
    $btnLaunch.FlatStyle = "Flat"
    $btnLaunch.FlatAppearance.BorderSize = 0
    $btnLaunch.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
    $btnLaunch.Cursor = [System.Windows.Forms.Cursors]::Hand
    $bottomPanel.Controls.Add($btnLaunch)

    # Tab Control
    $tabControl = New-Object System.Windows.Forms.TabControl
    $tabControl.Dock = "Fill"
    $form.Controls.Add($tabControl)
    $tabControl.BringToFront()

    $tabAccounts = New-Object System.Windows.Forms.TabPage
    $tabAccounts.Text = "  👤 Accounts  "
    $tabAccounts.BackColor = $BG_DARK
    $tabControl.TabPages.Add($tabAccounts)

    $tabPatcher = New-Object System.Windows.Forms.TabPage
    $tabPatcher.Text = "  🛠️ Patcher & Settings  "
    $tabPatcher.BackColor = $BG_DARK
    $tabControl.TabPages.Add($tabPatcher)

    # ---------------- TAB 1: ACCOUNTS ----------------
    # Form Card (Add Account)
    $formCard = New-Object System.Windows.Forms.Panel
    $formCard.Location = New-Object System.Drawing.Point(15, 15)
    $formCard.Size = New-Object System.Drawing.Size(635, 125)
    $formCard.Anchor = "Top,Left,Right"
    $formCard.BackColor = $BG_CARD
    $tabAccounts.Controls.Add($formCard)

    $lblAddTitle = New-Object System.Windows.Forms.Label
    $lblAddTitle.Text = "Add / Update Offline Account"
    $lblAddTitle.Font = New-Object System.Drawing.Font("Segoe UI", 10.5, [System.Drawing.FontStyle]::Bold)
    $lblAddTitle.Location = New-Object System.Drawing.Point(15, 10)
    $lblAddTitle.AutoSize = $true
    $formCard.Controls.Add($lblAddTitle)

    # Username Field
    $lblUser = New-Object System.Windows.Forms.Label
    $lblUser.Text = "Username:"
    $lblUser.Location = New-Object System.Drawing.Point(15, 42)
    $lblUser.AutoSize = $true
    $formCard.Controls.Add($lblUser)

    $txtUser = New-Object System.Windows.Forms.TextBox
    $txtUser.Location = New-Object System.Drawing.Point(120, 39)
    $txtUser.Size = New-Object System.Drawing.Size(190, 25)
    $txtUser.BackColor = $BG_INPUT
    $txtUser.ForeColor = $FG_TEXT
    $txtUser.BorderStyle = "FixedSingle"
    $formCard.Controls.Add($txtUser)

    # Skin Field
    $lblSkin = New-Object System.Windows.Forms.Label
    $lblSkin.Text = "Skin Name:"
    $lblSkin.Location = New-Object System.Drawing.Point(15, 75)
    $lblSkin.AutoSize = $true
    $formCard.Controls.Add($lblSkin)

    $txtSkin = New-Object System.Windows.Forms.TextBox
    $txtSkin.Location = New-Object System.Drawing.Point(120, 72)
    $txtSkin.Size = New-Object System.Drawing.Size(190, 25)
    $txtSkin.BackColor = $BG_INPUT
    $txtSkin.ForeColor = $FG_TEXT
    $txtSkin.BorderStyle = "FixedSingle"
    $formCard.Controls.Add($txtSkin)

    $lblSkinHint = New-Object System.Windows.Forms.Label
    $lblSkinHint.Text = "(e.g. Technoblade, Dream, Steve, or empty)"
    $lblSkinHint.ForeColor = $FG_MUTED
    $lblSkinHint.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $lblSkinHint.Location = New-Object System.Drawing.Point(120, 100)
    $lblSkinHint.AutoSize = $true
    $formCard.Controls.Add($lblSkinHint)

    # Add Button
    $btnAdd = New-Object System.Windows.Forms.Button
    $btnAdd.Text = "➕ Add / Update"
    $btnAdd.Size = New-Object System.Drawing.Size(140, 45)
    $btnAdd.Location = New-Object System.Drawing.Point(340, 48)
    $btnAdd.BackColor = $ACCENT_GREEN
    $btnAdd.ForeColor = [System.Drawing.Color]::White
    $btnAdd.FlatStyle = "Flat"
    $btnAdd.FlatAppearance.BorderSize = 0
    $btnAdd.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
    $btnAdd.Cursor = [System.Windows.Forms.Cursors]::Hand
    $formCard.Controls.Add($btnAdd)

    # Accounts List Card
    $listCard = New-Object System.Windows.Forms.Panel
    $listCard.Location = New-Object System.Drawing.Point(15, 150)
    $listCard.Size = New-Object System.Drawing.Size(635, 235)
    $listCard.Anchor = "Top,Bottom,Left,Right"
    $listCard.BackColor = $BG_CARD
    $tabAccounts.Controls.Add($listCard)

    $lblListTitle = New-Object System.Windows.Forms.Label
    $lblListTitle.Text = "Configured Accounts"
    $lblListTitle.Font = New-Object System.Drawing.Font("Segoe UI", 10.5, [System.Drawing.FontStyle]::Bold)
    $lblListTitle.Location = New-Object System.Drawing.Point(15, 10)
    $lblListTitle.AutoSize = $true
    $listCard.Controls.Add($lblListTitle)

    # ListBox
    $lstAccounts = New-Object System.Windows.Forms.ListBox
    $lstAccounts.Location = New-Object System.Drawing.Point(15, 38)
    $lstAccounts.Size = New-Object System.Drawing.Size(605, 140)
    $lstAccounts.Anchor = "Top,Bottom,Left,Right"
    $lstAccounts.BackColor = $BG_INPUT
    $lstAccounts.ForeColor = $FG_TEXT
    $lstAccounts.BorderStyle = "FixedSingle"
    $lstAccounts.Font = New-Object System.Drawing.Font("Consolas", 10)
    $listCard.Controls.Add($lstAccounts)

    # Action Buttons inside Accounts Card
    $btnSetActive = New-Object System.Windows.Forms.Button
    $btnSetActive.Text = "⭐ Set as Active"
    $btnSetActive.Size = New-Object System.Drawing.Size(130, 32)
    $btnSetActive.Location = New-Object System.Drawing.Point(15, 190)
    $btnSetActive.Anchor = "Bottom,Left"
    $btnSetActive.BackColor = $ACCENT_BLUE
    $btnSetActive.ForeColor = [System.Drawing.Color]::White
    $btnSetActive.FlatStyle = "Flat"
    $btnSetActive.FlatAppearance.BorderSize = 0
    $btnSetActive.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $btnSetActive.Cursor = [System.Windows.Forms.Cursors]::Hand
    $listCard.Controls.Add($btnSetActive)

    $btnDelete = New-Object System.Windows.Forms.Button
    $btnDelete.Text = "🗑️ Delete Account"
    $btnDelete.Size = New-Object System.Drawing.Size(135, 32)
    $btnDelete.Location = New-Object System.Drawing.Point(155, 190)
    $btnDelete.Anchor = "Bottom,Left"
    $btnDelete.BackColor = $ACCENT_RED
    $btnDelete.ForeColor = [System.Drawing.Color]::White
    $btnDelete.FlatStyle = "Flat"
    $btnDelete.FlatAppearance.BorderSize = 0
    $btnDelete.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $btnDelete.Cursor = [System.Windows.Forms.Cursors]::Hand
    $listCard.Controls.Add($btnDelete)

    $btnDeleteAll = New-Object System.Windows.Forms.Button
    $btnDeleteAll.Text = "🧹 Remove All"
    $btnDeleteAll.Size = New-Object System.Drawing.Size(115, 32)
    $btnDeleteAll.Location = New-Object System.Drawing.Point(300, 190)
    $btnDeleteAll.Anchor = "Bottom,Left"
    $btnDeleteAll.BackColor = [System.Drawing.ColorTranslator]::FromHtml("#5a6268")
    $btnDeleteAll.ForeColor = [System.Drawing.Color]::White
    $btnDeleteAll.FlatStyle = "Flat"
    $btnDeleteAll.FlatAppearance.BorderSize = 0
    $btnDeleteAll.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $btnDeleteAll.Cursor = [System.Windows.Forms.Cursors]::Hand
    $listCard.Controls.Add($btnDeleteAll)

    # ---------------- TAB 2: PATCHER ----------------
    $patchCard = New-Object System.Windows.Forms.Panel
    $patchCard.Location = New-Object System.Drawing.Point(15, 15)
    $patchCard.Size = New-Object System.Drawing.Size(635, 370)
    $patchCard.Anchor = "Top,Bottom,Left,Right"
    $patchCard.BackColor = $BG_CARD
    $tabPatcher.Controls.Add($patchCard)

    $lblPatchTitle = New-Object System.Windows.Forms.Label
    $lblPatchTitle.Text = "Lunar Client Windows Patcher & Settings"
    $lblPatchTitle.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $lblPatchTitle.Location = New-Object System.Drawing.Point(15, 12)
    $lblPatchTitle.AutoSize = $true
    $patchCard.Controls.Add($lblPatchTitle)

    $lblTargetPath = New-Object System.Windows.Forms.Label
    $lblTargetPath.Text = "Target Path (app.asar or Lunar Client.exe):"
    $lblTargetPath.Location = New-Object System.Drawing.Point(15, 45)
    $lblTargetPath.AutoSize = $true
    $patchCard.Controls.Add($lblTargetPath)

    $txtTarget = New-Object System.Windows.Forms.TextBox
    $txtTarget.Location = New-Object System.Drawing.Point(15, 70)
    $txtTarget.Size = New-Object System.Drawing.Size(510, 25)
    $txtTarget.Anchor = "Top,Left,Right"
    $txtTarget.BackColor = $BG_INPUT
    $txtTarget.ForeColor = $FG_TEXT
    $txtTarget.BorderStyle = "FixedSingle"
    $txtTarget.Text = (Find-LunarAsar)
    $patchCard.Controls.Add($txtTarget)

    $btnBrowse = New-Object System.Windows.Forms.Button
    $btnBrowse.Text = "Browse..."
    $btnBrowse.Location = New-Object System.Drawing.Point(535, 68)
    $btnBrowse.Size = New-Object System.Drawing.Size(85, 27)
    $btnBrowse.Anchor = "Top,Right"
    $btnBrowse.BackColor = $BG_INPUT
    $btnBrowse.ForeColor = $FG_TEXT
    $btnBrowse.FlatStyle = "Flat"
    $btnBrowse.Cursor = [System.Windows.Forms.Cursors]::Hand
    $patchCard.Controls.Add($btnBrowse)

    $lblPatchInfo = New-Object System.Windows.Forms.Label
    $lblPatchInfo.Text = "This patch modifies Lunar Client's internal authentication handler in app.asar so that offline accounts are accepted directly without connecting to Mojang's license server. A backup (app.asar.bak) is created automatically."
    $lblPatchInfo.ForeColor = $FG_MUTED
    $lblPatchInfo.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $lblPatchInfo.Location = New-Object System.Drawing.Point(15, 105)
    $lblPatchInfo.Size = New-Object System.Drawing.Size(605, 38)
    $patchCard.Controls.Add($lblPatchInfo)

    $txtLog = New-Object System.Windows.Forms.TextBox
    $txtLog.Multiline = $true
    $txtLog.ScrollBars = "Vertical"
    $txtLog.ReadOnly = $true
    $txtLog.Location = New-Object System.Drawing.Point(15, 150)
    $txtLog.Size = New-Object System.Drawing.Size(605, 150)
    $txtLog.Anchor = "Top,Bottom,Left,Right"
    $txtLog.BackColor = $BG_INPUT
    $txtLog.ForeColor = $FG_TEXT
    $txtLog.BorderStyle = "FixedSingle"
    $txtLog.Font = New-Object System.Drawing.Font("Consolas", 9)
    $patchCard.Controls.Add($txtLog)

    $btnDoPatch = New-Object System.Windows.Forms.Button
    $btnDoPatch.Text = "🛠️ Apply Offline Patch / Fix"
    $btnDoPatch.Size = New-Object System.Drawing.Size(210, 36)
    $btnDoPatch.Location = New-Object System.Drawing.Point(15, 315)
    $btnDoPatch.Anchor = "Bottom,Left"
    $btnDoPatch.BackColor = $ACCENT_GREEN
    $btnDoPatch.ForeColor = [System.Drawing.Color]::White
    $btnDoPatch.FlatStyle = "Flat"
    $btnDoPatch.FlatAppearance.BorderSize = 0
    $btnDoPatch.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
    $btnDoPatch.Cursor = [System.Windows.Forms.Cursors]::Hand
    $patchCard.Controls.Add($btnDoPatch)

    # ---------------- INTERACTIVITY & EVENTS ----------------
    $script:AccountKeys = [System.Collections.Generic.List[string]]::new()

    $RefreshUI = {
        $lstAccounts.Items.Clear()
        $script:AccountKeys.Clear()
        $data = Load-Accounts -autoRefresh $false
        $activeId = $data.activeAccountLocalId
        $accounts = $data.accounts
        if ($accounts) {
            foreach ($lid in $accounts.Keys) {
                $acc = $accounts[$lid]
                $u = $acc.username
                $act = if ($lid -eq $activeId) { " [ACTIVE]" } else { "" }
                $uuid = if ($acc.minecraftProfile -and $acc.minecraftProfile.id) { $acc.minecraftProfile.id.Substring(0, 8) } else { "" }
                $lstAccounts.Items.Add("• $u$act (UUID: $uuid...)") | Out-Null
                $script:AccountKeys.Add($lid) | Out-Null
            }
        }
    }

    $btnAdd.Add_Click({
        $u = $txtUser.Text.Trim()
        $s = $txtSkin.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($u)) {
            [System.Windows.Forms.MessageBox]::Show("Please enter a Minecraft username.", "Input Required", "OK", "Warning")
            return
        }
        $lblStatus.Text = "Adding account '$u'..."
        $form.Update()
        try {
            Add-OfflineAccount $u $s | Out-Null
            & $RefreshUI
            $lblStatus.Text = "Account '$u' added and set as active!"
            $txtUser.Text = ""
            $txtSkin.Text = ""
            [System.Windows.Forms.MessageBox]::Show("Offline account '$u' created and set as active!", "Success", "OK", "Information")
        } catch {
            $lblStatus.Text = "Error adding account."
            [System.Windows.Forms.MessageBox]::Show("Failed to add account: $_", "Error", "OK", "Error")
        }
    })

    $btnSetActive.Add_Click({
        $idx = $lstAccounts.SelectedIndex
        if ($idx -lt 0 -or $idx -ge $script:AccountKeys.Count) {
            [System.Windows.Forms.MessageBox]::Show("Please select an account from the list.", "Select Account", "OK", "Warning")
            return
        }
        $targetLid = $script:AccountKeys[$idx]
        try {
            Set-ActiveAccount $targetLid | Out-Null
            & $RefreshUI
            $lblStatus.Text = "Account set as active!"
        } catch {
            [System.Windows.Forms.MessageBox]::Show("Failed to set active account: $_", "Error", "OK", "Error")
        }
    })

    $btnDelete.Add_Click({
        $idx = $lstAccounts.SelectedIndex
        if ($idx -lt 0 -or $idx -ge $script:AccountKeys.Count) {
            [System.Windows.Forms.MessageBox]::Show("Please select an account from the list to delete.", "Select Account", "OK", "Warning")
            return
        }
        $targetLid = $script:AccountKeys[$idx]
        $res = [System.Windows.Forms.MessageBox]::Show("Are you sure you want to delete this offline account?", "Confirm Delete", "YesNo", "Question")
        if ($res -eq "Yes") {
            try {
                $deletedName = Remove-Account $targetLid
                & $RefreshUI
                $lblStatus.Text = "Account '$deletedName' removed."
                [System.Windows.Forms.MessageBox]::Show("Account '$deletedName' was removed.", "Deleted", "OK", "Information")
            } catch {
                [System.Windows.Forms.MessageBox]::Show("Failed to delete account: $_", "Error", "OK", "Error")
            }
        }
    })

    $btnDeleteAll.Add_Click({
        if ($script:AccountKeys.Count -eq 0) {
            [System.Windows.Forms.MessageBox]::Show("There are no accounts to remove.", "No Accounts", "OK", "Information")
            return
        }
        $res = [System.Windows.Forms.MessageBox]::Show("Are you sure you want to remove ALL offline accounts?", "Confirm Delete All", "YesNo", "Warning")
        if ($res -eq "Yes") {
            Remove-AllAccounts
            & $RefreshUI
            $lblStatus.Text = "All accounts removed."
            [System.Windows.Forms.MessageBox]::Show("All offline accounts have been removed.", "Removed", "OK", "Information")
        }
    })

    $btnBrowse.Add_Click({
        $dlg = New-Object System.Windows.Forms.OpenFileDialog
        $dlg.Filter = "Lunar Client Files (*.asar;*.exe)|*.asar;*.exe|ASAR Archive (*.asar)|*.asar|Executable (*.exe)|*.exe|All Files (*.*)|*.*"
        if ($dlg.ShowDialog() -eq "OK") {
            $txtTarget.Text = $dlg.FileName
        }
    })

    $btnDoPatch.Add_Click({
        $t = $txtTarget.Text.Trim()
        if ([string]::IsNullOrWhiteSpace($t) -or -not (Test-Path $t)) {
            [System.Windows.Forms.MessageBox]::Show("Please select a valid Lunar Client target (app.asar or Lunar Client.exe).", "Error", "OK", "Error")
            return
        }
        $txtLog.Clear()
        $lblStatus.Text = "Patching Lunar Client..."
        $form.Update()

        $logCb = {
            param([string]$m)
            $txtLog.AppendText("$m`r`n")
            $form.Update()
        }

        try {
            Patch-LunarTarget $t $logCb | Out-Null
            $lblStatus.Text = "Patching completed successfully!"
            [System.Windows.Forms.MessageBox]::Show("Lunar Client patched successfully!`nYou can now launch and play offline.", "Success", "OK", "Information")
        } catch {
            $lblStatus.Text = "Patching failed."
            & $logCb "[ERROR] $_"
            [System.Windows.Forms.MessageBox]::Show("Failed to patch Lunar Client:`n$_", "Patch Error", "OK", "Error")
        }
    })

    $btnLaunch.Add_Click({
        $t = $txtTarget.Text.Trim()
        $lblStatus.Text = "Launching Lunar Client..."
        $form.Update()
        try {
            Launch-LunarClient $t
            $lblStatus.Text = "Lunar Client launched!"
        } catch {
            $lblStatus.Text = "Launch failed."
            [System.Windows.Forms.MessageBox]::Show("Failed to launch Lunar Client:`n$_", "Launch Error", "OK", "Error")
        }
    })

    # Initial Refresh
    & $RefreshUI
    $form.ShowDialog() | Out-Null
}

# ==============================================================================
# CLI Entry Point
# ==============================================================================

if ($Command -eq "gui" -and [string]::IsNullOrWhiteSpace($Username) -and [string]::IsNullOrWhiteSpace($Target)) {
    Show-GUI
} elseif ($Command -eq "add") {
    $entry = Add-OfflineAccount $Username $Skin
    Write-Host "[✓] Added offline account: $($entry.username)"
    Write-Host "    UUID: $($entry.minecraftProfile.id)"
} elseif ($Command -eq "list") {
    $data = Load-Accounts
    $accounts = $data.accounts
    Write-Host "Total Accounts: $($accounts.Count)"
    Write-Host ("-" * 40)
    foreach ($lid in $accounts.Keys) {
        $acc = $accounts[$lid]
        $act = if ($lid -eq $data.activeAccountLocalId) { " [ACTIVE]" } else { "" }
        Write-Host "• $($acc.username)$act (ID: $lid)"
    }
} elseif ($Command -eq "set-active") {
    $acc = Set-ActiveAccount $Username
    Write-Host "[✓] Set '$($acc.username)' as active account."
} elseif ($Command -in @("delete", "remove", "rm")) {
    if ($Username -eq "--all" -or $Username -eq "-a") {
        Remove-AllAccounts
        Write-Host "[✓] All offline accounts removed."
    } else {
        $deleted = Remove-Account $Username
        Write-Host "[✓] Deleted account '$deleted'."
    }
} elseif ($Command -eq "patch") {
    Patch-LunarTarget $Target
} elseif ($Command -eq "launch") {
    Launch-LunarClient $Target
} else {
    Show-GUI
}
