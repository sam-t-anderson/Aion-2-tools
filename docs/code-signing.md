# Code signing policy

The Windows releases are not code-signed yet, so Windows names no publisher for them:
- **SmartScreen** warns about the download ("Windows protected your PC"): choose **More info → Run
  anyway** on the first launch.
- **Smart App Control** (Windows 11) blocks the app outright ("Smart App Control blocked an app
  that may be unsafe … could not verify its publisher"). It has no "Run anyway" and no per-app
  exception. Until the releases are signed, the only way to run the app on such a computer is to
  turn Smart App Control off: **Windows Security → App & browser control → Smart App Control
  settings → Off**. Builds of Windows 11 updated from April 2026 let you turn it back on there
  later; on older builds, turning it off stays off until Windows is reset or reinstalled. See
  [installing on Windows](install.md#windows-11-smart-app-control).

A valid signature is what Smart App Control accepts for an app it has no reputation for, so signing
the releases is the fix. The release workflow is ready to sign them with
[Azure Artifact Signing](https://learn.microsoft.com/azure/artifact-signing/) (below);
[SignPath Foundation](https://signpath.org) signs open-source projects for free, on application.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [sam-t-anderson](https://github.com/sam-t-anderson) |
| Approvers (merge the release pull requests that publish a release) | [sam-t-anderson](https://github.com/sam-t-anderson) |

Every release is built from this repository by GitHub Actions (`.github/workflows/ci.yml`); only
files that workflow builds are signed, from the repository's own release variables and secrets.

## Privacy

This program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it. In detail:

| When | Connects to | Sends |
|---|---|---|
| At launch (skip with `--no-sync`) | metabot.gg | requests for public game data and icons; nothing about you |
| When the app window opens | fonts.googleapis.com | a request for the Noto Sans font; nothing about you |
| At launch, when a window opens, then hourly (a failed check is retried within minutes) | api.github.com | a request for the latest release of this app; nothing about you |
| When you import a character | the official AION 2 site | the character name and server you search for |
| When you import a fight by link | abysslogs.com or a2dil.com | the link you paste |
| When you share a fight | the log server you set in **Settings** | that fight (and the character's stats when known) |
| With a log server set | that log server | requests for its public class statistics; nothing about you |

Everything else (your characters, fights, inventory and settings) stays in the data folder on your
computer. The installer changes no system settings, and the app uninstalls from **Settings →
Apps** (Windows) or by deleting it; your data folder is kept until you delete it.

## Turning on signing (maintainers)

The Windows build in `.github/workflows/ci.yml` signs the release once an Azure Artifact Signing
account is set up; until the repository variable below exists, those steps are skipped and the
release is published unsigned. When they run, the build:
1. signs every file of the app bundle that runs as code and is not signed already (`aion2calc.exe`
   and the Python extension modules; Python's own DLLs and the Visual C++ runtime come signed);
2. builds the installer from the signed files and signs the installer;
3. fails if any of those files is left without a valid signature.

The signed files name the account's validated identity as their publisher. Artifact Signing costs
about 10 USD a month (the Basic plan) and, for an individual, validates a person living in the
United States or Canada; an organization needs three years of verifiable history.

1. Turn on two-factor authentication on every account with write access to this repository.
2. In the [Azure portal](https://portal.azure.com), create an **Artifact Signing account** (the
   service was called Trusted Signing). Note its **endpoint** (it depends on the region, for example
   `https://eus.codesigning.azure.net/`) and its name.
3. In the account, complete **identity validation** (Public, for the person or organization that
   publishes the app), then create a **certificate profile** of type **Public Trust** from it.
4. In **Microsoft Entra ID → App registrations**, register an app for the release workflow and
   create a client secret for it. In the signing account's **Access control (IAM)**, give that app
   the role **Artifact Signing Certificate Profile Signer**.
5. In this repository, **Settings → Secrets and variables → Actions**:
   * variables `AZURE_SIGNING_ENDPOINT` (the endpoint), `AZURE_SIGNING_ACCOUNT` (the account name)
     and `AZURE_SIGNING_PROFILE` (the certificate profile's name);
   * secrets `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` and `AZURE_CLIENT_SECRET` (the app registration's
     directory ID, application ID and secret).
6. Publish a release as usual and check that the Windows build's **Check the signatures** step
   passed. Right-click the installed `aion2calc.exe` → **Properties → Digital Signatures** shows the
   signer.

Not signed yet: the uninstaller Inno Setup writes at install time (`unins000.exe`). Signing it
needs a sign tool the installer compiler runs (`SignTool` with `SignedUninstaller=yes` in
`packaging/windows/aion2calc.iss`), which is the next step once the account exists. Until then,
Smart App Control can block uninstalling from **Settings → Apps**; deleting the install folder
removes the app.

The executable and the installer carry the product name `aion2calc` and the release version in
their file properties.

### SignPath Foundation (free, on application)

[SignPath Foundation](https://signpath.org) signs open-source projects for free: free code signing
provided by [SignPath.io](https://about.signpath.io), certificate by SignPath Foundation, and signed
files name **SignPath Foundation** as the publisher. It reviews each project before accepting it
(apply at <https://signpath.org/apply.html>), and each signing request is approved by hand. Its
GitHub integration signs a build artifact after it is built, so the installer would have to be
built from files SignPath had already signed: the workflow would send the app bundle for signing
first, then build and send the installer. That workflow is not written yet; Azure Artifact Signing
above needs no application.
