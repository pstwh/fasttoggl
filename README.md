# fasttoggl

CLI to log work hours to Toggl from voice notes using an LLM. It records audio, transcribes and parses your description into activities, and logs them to Toggl. It also includes helpers to list/create projects, create manual time entries, and export detailed reports as PDF.

## Features

- **Audio capture**: Record a microphone note describing your work
- **LLM processing**: Uses an LLM (default: Gemini 2.5 Flash) to extract activities
- **Toggl integration**: Logs time entries via Toggl APIs
- **Project management**: Optionally create missing projects on the fly
- **Credential management**: Local secure storage for Toggl and optional LLM settings

## Installation

```bash
uv pip install git+https://github.com/pstwh/fasttoggl.git
```

## Configuration

### 1) Configure Toggl credentials

```bash
fasttoggl auth setup
```

You will be prompted for:
- Email (your Toggl email)
- API token (use your Toggl API token)
- Optional LLM settings: provider (default: google), model (default: gemini-2.5-flash), API key
- Language for prompts (default: pt-BR)

Credentials are stored locally.

## Usage

### Voice-to-Toggl flow

```bash
fasttoggl audio [OPTIONS]
```

Examples:

```bash
fasttoggl audio

# Use an existing wav file
fasttoggl audio -i audio.wav

# Record and save to a specific file
fasttoggl audio -o my_recording.wav
```

During processing you can:
- `a` record a new audio and process again
- `s` save the current result to Toggl
- `q` quit without saving

If a referenced project does not exist, you will be asked whether to create it automatically.

### System prompt

```bash
fasttoggl prompt
```

Opens your editor to customize the system prompt used by the LLM.

### Toggl helper commands

List data:

```bash
fasttoggl toggl orgs
fasttoggl toggl workspaces
fasttoggl toggl projects [--workspace-id ID]
fasttoggl toggl time-entries [--since DAYS | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--limit N]
```

Create data:

```bash
fasttoggl toggl create-project --workspace-id ID --name "Project Name"
fasttoggl toggl create-time-entry --project-id ID --start HH:MM --end HH:MM --description "Desc" [--date YYYY-MM-DD]
```

Export detailed reports as PDF:

```bash
# Explicit clients and date range/month
fasttoggl toggl report-pdf --workspace-id ID --client-ids 111 222 [--month YYYY-MM | --start-date YYYY-MM-DD --end-date YYYY-MM-DD] [--output FILE] [--prefix PREFIX]

# Auto-detect clients with hours for the month (workspace optional, defaults to first)
fasttoggl toggl fast-report-pdf [--workspace-id ID] [--month YYYY-MM] [--prefix PREFIX]
```

## How it works

1) Audio is recorded as WAV with defaults: 44100 Hz, mono.

2) The LLM transcribes and parses your description, identifies activities with start/end times, matches projects, and may suggest creating missing projects.

3) When saving, entries are created in Toggl with the parsed times for the current day. Time zone is handled automatically based on your system settings.

## Activity tips for voice input

- **Work hours**: e.g., 09:00 to 18:00 (with break 12:00–13:00)
- **Description**: Detailed and formal enough for HR approvals
- **Projects**: Use exact project names as in Toggl

Example:

"From 9 to 11 I worked on the authentication API. From 11 to 12 I reviewed the frontend code. After lunch, from 13 to 15 I wrote integration tests. From 15 to 17 I attended a planning meeting."
