# Code signing policy

Windows warns about downloads that are not code-signed ("Windows protected your PC"). Until the
builds are signed, choose **More info → Run anyway** on the first launch.

The Windows releases are going to be signed through [SignPath Foundation](https://signpath.org),
which signs open-source projects for free: free code signing provided by
[SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org). Signed files show **SignPath Foundation** as the
publisher.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [sam-t-anderson](https://github.com/sam-t-anderson) |
| Approvers (approve each signing request) | [sam-t-anderson](https://github.com/sam-t-anderson) |

Every release is built from this repository by GitHub Actions (`.github/workflows/ci.yml`); only
files that workflow builds are signed, and each signing request is approved by hand.

## Privacy

This program will not transfer any information to other networked systems unless specifically
requested by the user or the person installing or operating it. In detail:

| When | Connects to | Sends |
|---|---|---|
| At launch (skip with `--no-sync`) | metabot.gg | requests for public game data and icons; nothing about you |
| When the app window opens | fonts.googleapis.com | a request for the Noto Sans font; nothing about you |
| Every few hours | api.github.com | a request for the latest release of this app; nothing about you |
| When you import a character | the official AION 2 site | the character name and server you search for |
| When you import a fight by link | abysslogs.com or a2dil.com | the link you paste |
| When you share a fight | the log server you set in **Settings** | that fight (and the character's stats when known) |
| With a log server set | that log server | requests for its public class statistics; nothing about you |

Everything else (your characters, fights, inventory and settings) stays in the data folder on your
computer. The installer changes no system settings, and the app uninstalls from **Settings →
Apps** (Windows) or by deleting it; your data folder is kept until you delete it.

## Turning on signing (maintainers)

The release workflow already contains the signing step. It runs only when the secret below
exists, so releases are published unsigned until then.

1. Turn on two-factor authentication for GitHub (and later SignPath) on every account with write
   access.
2. Apply at <https://signpath.org/apply.html> for this repository. SignPath Foundation reviews the
   project; this takes a while.
3. Once accepted, in SignPath:
   * note the **organization ID**;
   * create the project `aion2calc`, add **GitHub.com** as its trusted build system, and install
     the SignPath GitHub App on this repository;
   * give the project this artifact configuration (the Windows build artifact holds the
     installer and the portable zip):

     ```xml
     <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
       <zip-file>
         <pe-file path="aion2calc-setup-*.exe">
           <authenticode-sign/>
         </pe-file>
         <zip-file path="aion2calc-*-windows-portable.zip">
           <pe-file path="aion2calc/aion2calc.exe">
             <authenticode-sign/>
           </pe-file>
         </zip-file>
       </zip-file>
     </artifact-configuration>
     ```

   * create the signing policy `release-signing` with manual approval, and an API token for a
     user with submitter rights on it.
4. In this repository (**Settings → Secrets and variables → Actions**), add the secret
   `SIGNPATH_API_TOKEN` and the variable `SIGNPATH_ORGANIZATION_ID`. Different slugs go in the
   variables `SIGNPATH_PROJECT_SLUG` and `SIGNPATH_SIGNING_POLICY_SLUG`.
5. Publish a release as usual. The release job sends the Windows build to SignPath and waits:
   approve the request in SignPath, and the signed installer and portable zip are published.

The executable and the installer carry the product name `aion2calc` and the release version in
their file properties, which SignPath checks.

A paid alternative that does not require an application is Microsoft's Azure Trusted Signing
(about 10 USD a month; individuals in the US and Canada): it signs in your own name, with a
different workflow step.
