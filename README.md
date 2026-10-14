# DTS Fleet Overview

DTS Fleet Overview shows the latest temperature measurements from all our DTS systems in one full-screen window.

It logs in to IXON Cloud and connects to the InfluxDB database on the *Leak Detector 00 Cloud* device. From there it fetches the three most recent temperature traces from each DTS system. The window updates itself every 2 minutes until you close it.

**Already installed? Just want to start up the overview?**
1) Open VS Code. It normally reopens the **dts-fleet-overview** folder by itself. If not, use **File → Open Recent → dts-fleet-overview**.
2) Open a terminal with **Terminal → New Terminal**, and check that it ends with the right folder: **...\dts-fleet-overview>**
        *(If not, run this)*

        cd "$HOME\dts-fleet-overview"
3) Run:

        uv run main.py


**Reading the window**

- There is one plot per DTS system, showing temperature (°C) along the fiber (metres).
- The title shows the system name and how long ago its newest trace was measured.
- The plot colour shows whether the system is up to date:
  - **Green (live):** the newest trace is less than 4 minutes old.
  - **Grey (stale):** the newest trace is older than that, so the system may have stopped logging or lost its connection.
- The newest trace is drawn in full colour. Older traces fade into the background.
- "Updated HH:MM:SS" at the top shows when the window last refreshed.

---

## Installation, step by step

You only need to do this once. It takes about 10 minutes.

### 1. Install Visual Studio Code

If you already have VS Code, skip this step.

Download VS Code from [code.visualstudio.com](https://code.visualstudio.com), run the installer, and accept the default choices.

### 2. Open a terminal in VS Code

Open VS Code. In the menu at the top, choose **Terminal → New Terminal**. A panel with a blinking cursor opens at the bottom of the window. This is the terminal, where you paste the commands below.

To run a command, copy it from this page, click in the terminal, paste with **Ctrl+V**, and press **Enter**.

### 3. Install Git and uv

The program needs two free tools:
- **Git** unpacks the program file you received.
- **uv** runs the program, and downloads Python and everything else it needs automatically.

Paste these two commands, one at a time. Each one ends with a message saying the installation was successful, or that the tool is already installed. Both are fine.

```powershell
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
```

```powershell
winget install --id astral-sh.uv -e --accept-source-agreements --accept-package-agreements
```

Then **close VS Code completely and open it again**, and open a new terminal (**Terminal → New Terminal**). VS Code only recognises newly installed programs after a restart.

### 4. Unpack the program

You should have received a file called `dts-fleet-overview.bundle`. Save it in your **Downloads** folder. Then paste:

```powershell
git clone "$HOME\Downloads\dts-fleet-overview.bundle" "$HOME\dts-fleet-overview"
```

This creates a folder called `dts-fleet-overview` in your user folder (`C:\Users\<your name>\dts-fleet-overview`). Afterwards you can delete the `.bundle` file from Downloads.

### 5. Open the program folder in VS Code

1. Choose **File → Open Folder…**
2. Go to your user folder (`C:\Users\<your name>`), click **dts-fleet-overview** once, and click **Select Folder**.
3. If VS Code asks *"Do you trust the authors of the files in this folder?"*, choose **Yes, I trust the authors**.
4. Open a new terminal (**Terminal → New Terminal**). It now starts in the program folder, and the line ends with **...\dts-fleet-overview>**.

VS Code may suggest installing extensions. They're not needed, so you can close those messages.

### 6. Fill in your login details

The program needs your IXON login and an InfluxDB token. These are stored in a file called `.env`, which stays on your computer. Create it by pasting:

```powershell
Copy-Item .env.example .env
```

The file list on the left side of VS Code now shows `.env`. Click it to open it, and fill in the values after each `=` sign, with no spaces and no quotes:

| Setting | What to write |
|---|---|
| `IXON_EMAIL` | The email address you use to log in to IXON Cloud |
| `IXON_PASS` | Your IXON password. You can leave this empty; the program will then ask for it in the terminal about once an hour. |
| `API_TOKEN` | The InfluxDB token. Ask the person who sent you the program for it. |

When you're done, it should look something like this:

```
IXON_EMAIL=ola.nordmann@leakdetector.no
IXON_PASS=MyPassword123
API_TOKEN=aBcD1234...
```

Save with **Ctrl+S**.

### 7. Start the program

```powershell
uv run main.py
```

Here "uv" will do the rest of the work for you. The first start takes a minute or two, while uv downloads Python and the libraries the program uses. After that, it starts in a few seconds.

If your IXON account uses two-factor authentication, the terminal asks for a code. Click in the terminal, type the code from your authenticator app, and press Enter.

The overview window then opens in full screen.

---

## Everyday use

1. Open VS Code. It normally reopens the **dts-fleet-overview** folder by itself. If not, use **File → Open Recent → dts-fleet-overview**.
2. Open a terminal (**Terminal → New Terminal**) and paste:
   ```powershell
   uv run main.py
   ```
3. Leave the overview window open for as long as you want to watch the systems; it updates itself every 2 minutes.
4. Close the overview window to stop the program.

Keep VS Code open while the program runs. The terminal shows what the program is doing, and asks for your IXON password or 2FA code when it needs them.

---

## Updating to a new version

When you receive a new `dts-fleet-overview.bundle`:

1. Delete the old `.bundle` file from Downloads, if it's still there, so the new one gets the same name.
2. Save the new file in Downloads.
3. Open the program folder in VS Code, open a terminal, and paste:
   ```powershell
   git pull "$HOME\Downloads\dts-fleet-overview.bundle" main
   ```

Your `.env` file with your login details is kept as it is.

---

## Troubleshooting

| Message | What to do |
|---|---|
| `git` / `uv` / `winget` *is not recognized* | Close VS Code completely and open it again. If `winget` is the one missing, install **App Installer** from the Microsoft Store first. |
| `KeyError: 'API_TOKEN'` or `KeyError: 'IXON_EMAIL'` | The `.env` file is missing or not filled in (step 6), or the terminal isn't in the program folder. Check that the terminal line ends with `...\dts-fleet-overview>`. |
| Errors mentioning `$HOME` or `Copy-Item` | The terminal isn't PowerShell. Click the small arrow next to **+** at the top right of the terminal panel and choose **PowerShell**. |
| `Ixon login failed` | Check the email address and password in `.env`. |
| `API token rejected (401)` | The InfluxDB token is wrong or has been deleted. Ask for a new one and put it in `.env`. |
| `fatal: destination path ... already exists` | The program is already installed. Skip to *Everyday use*, or see *Updating to a new version*. |

---

## For the maintainer: sharing a new version

Run this in the project folder to pack the current version into a single file:

```powershell
git bundle create dts-fleet-overview.bundle HEAD main
```

Send `dts-fleet-overview.bundle` to colleagues by email, Teams or similar. They follow *Installation* the first time, and *Updating to a new version* after that. Only committed changes are included, so commit before you create the bundle.
