# Installing GradeAudit

Prebuilt binaries for Linux, macOS, and Windows are attached to the
[`latest` release](https://github.com/Mahamadahir/markingAgent/releases/tag/latest).
Each one is a self-contained folder, so there is no installer to run. Download the
archive for your platform, extract it, and run the executable inside.

The builds are not code-signed, so the first launch shows a security warning on
each operating system. The steps below cover how to get past it.

## Before you start

GradeAudit calls a language model to grade scripts, so it needs an API key for
your chosen provider. Set the matching environment variable before launching:

| Provider | Variable |
|----------|----------|
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Google Gemini | `GOOGLE_API_KEY` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` |

You can also enter the key in the desktop app's Project Setup screen instead of
setting an environment variable.

## Linux

Download `GradeAudit-linux-x86_64.tar.gz`, then:

```bash
tar -xzf GradeAudit-linux-x86_64.tar.gz
cd GradeAudit
./GradeAudit
```

If the app fails with `Could not load the Qt platform plugin "xcb"`, install the
Qt runtime libraries:

```bash
sudo apt update
sudo apt install -y libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libegl1 libgl1
```

Then run `./GradeAudit` again.

## macOS (Apple Silicon)

The macOS build is for Apple Silicon (M1 and later) only. Intel Macs are not
supported by the prebuilt binary.

Download `GradeAudit-macos-arm64.tar.gz`, then:

```bash
tar -xzf GradeAudit-macos-arm64.tar.gz
xattr -dr com.apple.quarantine GradeAudit.app
```

Move `GradeAudit.app` to your Applications folder and open it as normal.

The `xattr` line clears the quarantine flag macOS puts on downloaded files.
Without it, Gatekeeper blocks the app because it is not signed, showing
"GradeAudit cannot be opened because the developer cannot be verified". Clearing
quarantine is the reliable fix; alternatively, right-click the app and choose
Open the first time to approve it.

## Windows

Download `GradeAudit-windows-x86_64.zip` and extract it (right-click, Extract
All). Open the extracted `GradeAudit` folder and run `GradeAudit.exe`.

The first launch shows "Windows protected your PC" from SmartScreen because the
app is unsigned. Click **More info**, then **Run anyway**.

If Windows Defender removes `GradeAudit.exe`, restore it from the quarantine list
in Windows Security and add the folder to your exclusions, or run the app from a
location Defender is not scanning aggressively.

## Building from source instead

If you would rather build it yourself, clone the repository and use the platform
build scripts in `scripts/`, or run the app directly from a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m marking_agent.desktop_app
```
