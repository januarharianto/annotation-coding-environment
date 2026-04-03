# ACE — Annotation Coding Environment

A simple qualitative text coding tool for small teams. ACE focuses on the text coding process itself and is minimalistic by design. 



## Install

ACE runs in your web browser, but you need to start it using a tool called **Terminal** (on Mac/Linux) or **PowerShell** (on Windows). Don't worry if you haven't used these before!

### Step 1: Open your command line tool
- **On Mac**: Open **Terminal**. You can find it by pressing `Cmd + Space` (Command and Space), typing "Terminal", and pressing Enter.
- **On Windows**: Open **PowerShell**. Click the Start Menu, type "PowerShell", and press Enter.

### Step 2: Install the package manager ("uv")
You only need to do this step the very first time you use ACE. Copy the text snippet for your computer below, paste it into your Terminal or PowerShell window, and press **Enter**.

**Mac and Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

*(Note: It might take a few seconds to download and install. Just wait until it finishes printing text to the screen. On Mac/Linux, you might need to close and reopen your Terminal after this step finishes before moving on to Step 3).*

### Step 3: Run ACE
Whenever you want to use ACE, just open your Terminal (Mac) or PowerShell (Windows) like you did in Step 1, copy and paste this command, and press **Enter**:

```bash
uvx ace-coder
```

ACE will automatically download its latest version, launch a small server on your computer, and open the app in your web browser! 

Keep that Terminal/PowerShell window open while you are coding. When you are done, you can safely close the window to stop ACE.

## Development

ACE is a Python app built with FastAPI and HTMX. To work on it locally:

```bash
git clone https://github.com/januarharianto/annotation-coding-environment.git
cd annotation-coding-environment
uv run ace
```

Run the tests:

```bash
uv run pytest
```

### Desktop app development

To work on the native desktop shell (requires Rust toolchain and Tauri CLI):

```bash
# Terminal 1: Python server with hot reload
uv run uvicorn ace.app:create_app --factory --host 127.0.0.1 --port 18080 --reload --reload-dir src/ace

# Terminal 2: Tauri dev shell
cd desktop && cargo tauri dev
```
