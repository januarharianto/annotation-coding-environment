# ACE — Annotation Coding Environment

ACE is a qualitative coding tool that I developed for use with my research group at The University of Sydney. We wanted a way to select sections of text and assign qualitative codes and annotations to them but found existing tools to be unintuitive. Most importantly, I realised that we were using perhaps 5% of the features of expensive commercial software. 

I am both a research software engineer and data scientist, so I "naturally" started working on a simple text highlight tool that ended up becoming ACE. ACE does only a few things right now. I do not intend to add anything more than the current feature set. These are what ACE does:

- Import your texts, build a codebook, highlight passages and assign codes and notes to sources
- Export your annotations and codebook for further analysis
- Compare coding across team members with built-in inter-coder reliability metrics

I may add more features in the near future, but right now I am hyper focused on making sure that ACE does the above in an extremely minimalist yet intuitive way. If I can get you to say "WOW!" while using ACE, then I am happy.

**Note: I use Anthropic's Claude as a copilot, but all code is audited and verified before they are pushed.** Just putting this here so that it can be part of your decision making process of whether to use ACE or not.

## Download

Pre-built installers are on the [Releases page](https://github.com/januarharianto/annotation-coding-environment/releases/latest):

- **macOS (Apple Silicon)** — `ACE_*_aarch64.dmg`. Open, drag ACE to Applications. First launch: right-click → Open to bypass Gatekeeper.
- **Windows** — `ACE_*_x64-setup.exe`. Run the installer. SmartScreen may warn — click "More info" → "Run anyway".

Intel Macs are not currently supported. Neither build is code-signed yet.

## Install from source

You need some experience with using the command line on eithr macOS or Windows. In the Terminal or PowerShell, first install uv. On the macOS and Linux:

```
curl -LsSf https://astral.sh/uv/install.sh | less
```

On Windows:

```
powershell -c "irm https://astral.sh/uv/install.ps1 | more"
```

Then, run the following commands:

```
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv run ace
```


ACE will open in your web browser.

In the future, you only need to run the following:


```
cd annotation-coding-environment
uv run ace
```
