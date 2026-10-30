# Code signing policy

The Windows releases are code-signed with [Azure Artifact Signing](https://learn.microsoft.com/azure/artifact-signing/)
since 0.2.346: the installer, `aion2calc.exe` and the app's Python extension modules, and from 0.2.347
the uninstaller (`unins000.exe`) as well. Windows names the publisher when the installer runs, and
Windows 11's Smart App Control, which blocks an app it has no reputation for unless the app carries a
valid signature, lets them run. Right-click a file → **Properties → Digital Signatures** shows the
signer, timestamped by Microsoft's timestamping service.

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
| At launch, when a window opens, then hourly (a failed check is retried within minutes) | api.github.com | a request for the latest release of this app; nothing about you |
| When you import a character | the official AION 2 site | the character name and server you search for |
| When you import a fight by link | abysslogs.com or a2dil.com | the link you paste |
| When you press **Load the interactive map** on the Maps page (or chose to load it automatically) | interactivemap.app | a request for the provider's map page, which loads its own scripts; nothing about you |
| When Gear & Advice shows a recommended Pantheon board | aion2hub.com | requests for the decorations' pictures by item id; nothing about you |
| When you share a fight | the log server you set in **Settings** | that fight (and the character's stats when known) |
| With a log server set | that log server | requests for its public class statistics; nothing about you |

Everything else (your characters, fights, inventory and settings) stays in the data folder on your
computer. The installer changes no system settings, and the app uninstalls from **Settings →
Apps** (Windows) or by deleting it; your data folder is kept until you delete it.

## Turning on signing (maintainers)

The Windows build in `.github/workflows/ci.yml` signs the release with the Azure Artifact Signing
account set up below; without the repository variable `AZURE_SIGNING_ENDPOINT`, those steps are
skipped and a release would be published unsigned. When they run, the build:
1. signs every file of the app bundle that runs as code and is not signed already (`aion2calc.exe`
   and the Python extension modules; Python's own DLLs and the Visual C++ runtime come signed);
2. builds the installer from the signed files; the installer compiler signs Setup and the
   uninstaller it writes (`unins000.exe`) with SignTool and Artifact Signing's SignTool plugin, since
   Inno Setup can sign the uninstaller only while it compiles;
3. fails if any of those files, or the uninstaller of the copy it installs, is left without a valid
   signature.

Each file signed takes one signature from the plan's monthly allowance (5,000 on the Basic plan),
about 44 a build. So only a build that publishes a new release is signed (a push to `main` with a new
version, or a `v*` tag), and a run started by hand (**Actions → CI → Run workflow**) to test the
setup. Pushes to other branches, pull requests and pushes to `main` that release nothing are not.
Every build that is not signed rehearses step 2 with a throwaway certificate instead, so a change
that would break signing the uninstaller shows up before a release.

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
6. Start **Actions → CI → Run workflow** on any branch and check that the Windows build's **Check
   the signatures** step passed; releases from then on are signed the same way. Right-click the
   installed `aion2calc.exe` (or `unins000.exe`) → **Properties → Digital Signatures** shows the
   signer.

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
