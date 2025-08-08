import argparse
import getpass
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from tzlocal import get_localzone_name

from fasttoggl.chains.chain import SYSTEM_INSTRUCTION
from fasttoggl.core.audio import record_audio
from fasttoggl.core.credentials import CredentialsManager
from fasttoggl.core.llm import process_audio_with_llm
from fasttoggl.data.toggl_client import TogglSessionClient

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"


def print_colorful_result(output: dict):
    try:
        print(f"{CYAN}{BOLD}Processing result{RESET}")
        missing_project = bool(output.get("missing_project"))
        missing_projects = output.get("missing_projects") or []
        create_project = bool(output.get("create_project"))
        project_name = output.get("project_name") or ""
        activities = output.get("activities") or []

        if missing_project:
            print(
                f"{YELLOW}Missing projects:{RESET} {', '.join(missing_projects) if missing_projects else '-'}"
            )
        if create_project:
            print(f"{MAGENTA}Suggested new project:{RESET} {project_name}")

        print()
        print(f"{BOLD}Activities ({len(activities)}):{RESET}")
        total_minutes = 0
        for idx, activity in enumerate(activities, 1):
            start_time = str(activity.get("start_time", ""))
            end_time = str(activity.get("end_time", ""))
            description = str(activity.get("description", "")).strip()
            project = str(activity.get("project", "")).strip()
            print(f"{GREEN}●{RESET} {start_time} - {end_time}  {BOLD}{project}{RESET}")
            if description:
                print(f"   {description}")
            try:
                sh, sm = map(int, start_time.split(":"))
                eh, em = map(int, end_time.split(":"))
                total_minutes += (eh * 60 + em) - (sh * 60 + sm)
            except Exception:
                pass
        if activities:
            hours = total_minutes // 60
            minutes = total_minutes % 60
            print()
            print(f"{BLUE}Total time:{RESET} {hours:02d}:{minutes:02d}")
        print()
    except Exception:
        print("Processing result:")
        print(json.dumps(output, indent=2, ensure_ascii=False))


def normalize_llm_output(output):
    if not isinstance(output, dict):
        return {
            "missing_project": False,
            "missing_projects": [],
            "create_project": False,
            "project_name": "",
            "activities": [],
        }
    result = {
        "missing_project": bool(output.get("missing_project", False)),
        "missing_projects": output.get("missing_projects") or [],
        "create_project": bool(output.get("create_project", False)),
        "project_name": output.get("project_name") or "",
        "activities": output.get("activities") or [],
    }
    return result


def get_system_offset_in_seconds() -> int:
    try:
        local_tz_name = get_localzone_name()
        local_timezone = ZoneInfo(local_tz_name)

    except Exception as e:
        print(f"Could not detect system timezone: {e}. Using UTC as default.")
        local_timezone = ZoneInfo("UTC")

    now_local = datetime.now(local_timezone)

    offset_timedelta = now_local.utcoffset()

    if offset_timedelta:
        return int(offset_timedelta.total_seconds())

    return 0


def setup_credentials():
    credentials_manager = CredentialsManager()

    if credentials_manager.credentials_exist():
        print(
            "Credentials already configured. Do you want to reconfigure? (y/N): ",
            end="",
        )
        response = input().strip().lower()
        if response not in ["y", "yes"]:
            return

    print("Toggl credentials setup (API Token)")
    print("\n")

    email = input("Enter your Toggl email: ").strip()
    password = getpass.getpass("Enter your Toggl API Token (Password): ")
    print("\nLLM configuration (optional)")
    llm_provider = input("Provider [google]: ").strip() or "google"
    llm_model = input("Model [gemini-2.5-flash]: ").strip() or "gemini-2.5-flash"
    llm_api_key = getpass.getpass("API Key (leave empty to skip): ")
    print("\nLanguage (default for prompts)")
    language = input("Language (default: pt-BR): ").strip() or "pt-BR"

    if not email or not password:
        print("Email and API token are required")
        return

    try:
        credentials_manager.save_credentials(
            email,
            password,
            llm_provider=llm_provider if llm_api_key else None,
            llm_model=llm_model if llm_api_key else None,
            llm_api_key=llm_api_key if llm_api_key else None,
            language=language,
        )
        print("Credentials saved successfully!")
    except Exception as e:
        print(f"Error saving credentials: {e}")


def force_credentials_setup():
    print("Toggl credentials not configured!")
    print("You must configure credentials before using the system.")
    print("\n")

    setup_credentials()


def check_credentials_and_fetch_data():
    credentials_manager = CredentialsManager()

    if not credentials_manager.credentials_exist():
        force_credentials_setup()
        if not credentials_manager.credentials_exist():
            print("Credential setup canceled or failed.")
            return None, None, None

    email, password = credentials_manager.load_credentials()

    if not email or not password:
        print("Error loading credentials")
        return None, None, None

    try:
        print("Authenticating with Toggl (Basic Auth with API Token)...")
        client = TogglSessionClient(email, password)
        print("Authentication successful!")

        print(f"\n{CYAN}{BOLD}Organizations{RESET}")
        organizations = client.get_organizations()
        print(f"{BOLD}Found:{RESET} {len(organizations)}")
        for org in organizations:
            print(f"{GREEN}●{RESET} {org.name} {YELLOW}(ID: {org.id}){RESET}")

        print(f"\n{CYAN}{BOLD}Workspaces{RESET}")
        workspaces = client.get_workspaces()
        print(f"{BOLD}Found:{RESET} {len(workspaces)}")
        for workspace in workspaces:
            print(
                f"{GREEN}●{RESET} {workspace.name} {YELLOW}(ID: {workspace.id}){RESET}"
            )

        print(f"\n{CYAN}{BOLD}Latest time entries{RESET}")
        latest_entries = client.get_latest_time_entries(10)
        if latest_entries:
            for te in latest_entries:
                print(
                    f"{GREEN}●{RESET} {BOLD}{te.start}{RESET} .. {BOLD}{te.stop}{RESET}"
                )
                if te.description:
                    print(f"   {te.description}")
        else:
            print("No entries found")

        print(f"\n{CYAN}{BOLD}Projects{RESET}")
        all_projects = []
        for workspace in workspaces:
            projects = client.get_projects(workspace.id)
            all_projects.extend(projects)
            print(
                f"\n{BOLD}Workspace:{RESET} {workspace.name} {YELLOW}(ID: {workspace.id}){RESET}"
            )
            for project in projects:
                client_label = project.client_name if project.client_name else "-"
                print(
                    f"{GREEN}●{RESET} {BOLD}({project.id}){RESET} {project.name} {YELLOW}(Client: {client_label}){RESET}"
                )

        print(f"\n{BLUE}Total projects:{RESET} {len(all_projects)}")

        return client, workspaces, all_projects

    except Exception as e:
        print(f"Error during authentication or data fetching: {e}")
        return None, None, None


def get_authenticated_client():
    credentials_manager = CredentialsManager()
    if not credentials_manager.credentials_exist():
        force_credentials_setup()
        if not credentials_manager.credentials_exist():
            print("Credential setup canceled or failed.")
            return None
    email, token = credentials_manager.load_credentials()
    if not email or not token:
        print("Error loading credentials")
        return None
    try:
        client = TogglSessionClient(email, token)
        return client
    except Exception as e:
        print(f"Error during authentication: {e}")
        return None


def cmd_audio(args):
    client, workspaces, projects = check_credentials_and_fetch_data()
    if client is None:
        print("Could not authenticate with Toggl. Aborting operation.")
        sys.exit(1)
    audio_file = None
    temp_file = None
    if args.output and args.input:
        print("Error: Cannot specify both --output and --input")
        sys.exit(1)
    if args.duration and args.duration <= 0:
        print("Error: Duration must be positive")
        sys.exit(1)
    if args.output and not args.output.endswith(".wav"):
        print("Warning: Output file should have .wav extension")
    if args.input and not args.input.endswith(".wav"):
        print("Warning: Input file should have .wav extension")
    if args.output:
        record_audio(
            output_file=args.output,
            duration=args.duration,
            sample_rate=args.sample_rate,
            channels=args.channels,
            chunk_size=args.chunk_size,
        )
        audio_file = args.output
    elif args.input:
        audio_file = args.input
    else:
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_file.close()
        record_audio(
            output_file=temp_file.name,
            duration=args.duration,
            sample_rate=args.sample_rate,
            channels=args.channels,
            chunk_size=args.chunk_size,
        )
        audio_file = temp_file.name
    if not args.no_llm:
        base_context = f"Projects: {projects}"
        current_audio_file = audio_file
        conversation_history = []
        last_was_project_created = False
        current_work_description = ""
        context = base_context
        while True:
            if conversation_history:
                context += "\n\nPrevious attempts history:\n"
                for i, attempt in enumerate(conversation_history, 1):
                    context += f"Attempt {i}: {attempt}\n"
            output_raw = process_audio_with_llm(context, current_audio_file, args.model)
            output = normalize_llm_output(output_raw)
            conversation_history.append(output)
            if output["missing_project"]:
                print(f"Projects not found: {output['missing_projects']}")
            if output["create_project"]:
                print("Do you want to create the project? (y/N): ", end="")
                print(f"Project name: {output['project_name']}")
                response = input().strip().lower()
                if response in ["y", "yes", "s", "sim"]:
                    print(f"Creating project: {output['project_name']}")
                    client.create_project(workspaces[0].id, output["project_name"])
                    print(f"Project created successfully: {output['project_name']}")
                    projects = client.get_projects(workspaces[0].id)
                    conversation_history.append(
                        f"New project created: {output['project_name']}"
                    )
                    conversation_history.append(f"Projects: {projects}")
                    conversation_history.append(
                        f"Current task description (before the new project): {current_work_description}"
                    )
                    last_was_project_created = True
            else:
                current_work_description = output["activities"]
            if last_was_project_created:
                output_raw = process_audio_with_llm(context, None, args.model)
                output = normalize_llm_output(output_raw)
                conversation_history.append(output)
                last_was_project_created = False
            print_colorful_result(output)
            print("\nOptions:")
            print("a - Record new audio and process again")
            print("s - Save current result")
            print("q - Quit")
            print("\nChoose an option: ", end="")
            response = input().strip().lower()
            if response == "a":
                print("\nRecording new audio...")
                if temp_file:
                    new_temp_file = tempfile.NamedTemporaryFile(
                        suffix=".wav", delete=False
                    )
                    new_temp_file.close()
                    new_audio_file = new_temp_file.name
                    if os.path.exists(current_audio_file):
                        os.unlink(current_audio_file)
                    temp_file = new_temp_file
                else:
                    new_audio_file = "temp_audio.wav"
                record_audio(
                    output_file=new_audio_file,
                    duration=args.duration,
                    sample_rate=args.sample_rate,
                    channels=args.channels,
                    chunk_size=args.chunk_size,
                )
                current_audio_file = new_audio_file
                continue
            elif response == "s":
                print("\nSaving current result...")
                for activity in output["activities"]:
                    now = datetime.now(timezone.utc)
                    start_hour, start_minute = map(
                        int, activity["start_time"].split(":")
                    )
                    end_hour, end_minute = map(int, activity["end_time"].split(":"))
                    start_time = now.replace(
                        hour=start_hour, minute=start_minute, second=0, microsecond=0
                    )
                    end_time = now.replace(
                        hour=end_hour, minute=end_minute, second=0, microsecond=0
                    )
                    system_offset = get_system_offset_in_seconds()
                    start_time = start_time - timedelta(seconds=system_offset)
                    end_time = end_time - timedelta(seconds=system_offset)
                    project = None
                    for p in projects:
                        if p.name == activity["project"]:
                            project = p
                            break
                    if project is None:
                        print(f"✗ Project not found: {activity['project']}")
                        continue
                    try:
                        client.put_hours(
                            project, start_time, end_time, activity["description"]
                        )
                        print(
                            f"\033[32m✓ Logged: {activity['start_time']} - {activity['end_time']} - {activity['description']} - {project.name}\033[0m"
                        )
                    except Exception as e:
                        print(
                            f"\033[31m✗ Error logging: {activity['start_time']} - {activity['end_time']} - {activity['description']} - {project.name}\033[0m"
                        )
                        print(f"\033[31m  Error: {e}\033[0m")
                break
            elif response == "q":
                break
    if temp_file and os.path.exists(temp_file.name):
        os.unlink(temp_file.name)


def toggl_orgs(_args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    orgs = client.get_organizations()
    for org in orgs:
        print(f"{org.id}\t{org.name}")


def toggl_workspaces(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    workspaces = client.get_workspaces()
    for ws in workspaces:
        print(f"{ws.id}\t{ws.name}")


def toggl_projects(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    workspaces = client.get_workspaces()
    if args.workspace_id:
        wids = [args.workspace_id]
    else:
        wids = [w.id for w in workspaces]
    for wid in wids:
        projects = client.get_projects(wid)
        for p in projects:
            print(f"{p.id}\t{p.workspace_id}\t{p.name}")


def toggl_time_entries(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    entries = client.get_time_entries(
        since=args.since,
        before=args.before,
        start_date=args.start_date,
        end_date=args.end_date,
        meta=None,
        include_sharing=None,
    )
    if args.limit:
        try:
            entries = sorted(entries, key=lambda e: e.start or "", reverse=True)[
                : args.limit
            ]
        except Exception:
            entries = entries[: args.limit]
    for e in entries:
        print(f"{e.id}\t{e.start}\t{e.stop}\t{e.description}")


def toggl_create_project(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    project = client.create_project(args.workspace_id, args.name)
    if project is None:
        print("Error creating project")
        sys.exit(1)
    print(f"{project.id}\t{project.workspace_id}\t{project.name}")


def toggl_create_time_entry(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    projects = client.get_all_projects()
    project = None
    for p in projects:
        if p.id == args.project_id:
            project = p
            break
    if project is None:
        print("Project not found")
        sys.exit(1)
    if args.date:
        try:
            base_date = datetime.fromisoformat(args.date).replace(tzinfo=timezone.utc)
        except Exception:
            print("Invalid date, use YYYY-MM-DD")
            sys.exit(1)
    else:
        base_date = datetime.now(timezone.utc)
    try:
        start_hour, start_minute = map(int, args.start.split(":"))
        end_hour, end_minute = map(int, args.end.split(":"))
    except Exception:
        print("Invalid times, use HH:MM")
        sys.exit(1)
    start_time = base_date.replace(
        hour=start_hour, minute=start_minute, second=0, microsecond=0
    )
    end_time = base_date.replace(
        hour=end_hour, minute=end_minute, second=0, microsecond=0
    )
    system_offset = get_system_offset_in_seconds()
    start_time = start_time - timedelta(seconds=system_offset)
    end_time = end_time - timedelta(seconds=system_offset)
    if end_time <= start_time:
        print("End must be greater than start")
        sys.exit(1)
    try:
        client.put_hours(project, start_time, end_time, args.description)
        print(
            f"{project.id}\t{project.workspace_id}\t{args.start}-{args.end}\t{args.description}"
        )
    except Exception as e:
        print(f"Error creating time entry: {e}")
        sys.exit(1)


def month_range(year: int, month: int) -> tuple[str, str]:
    dt = datetime(year, month, 1)
    next_month = (dt.replace(day=28) + timedelta(days=4)).replace(day=1)
    start_date = dt.strftime("%Y-%m-%d")
    end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    return start_date, end_date


def _safe_name(value: str) -> str:
    s = value.strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9._-]", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def toggl_report_pdf(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    if args.month and (args.start_date or args.end_date):
        print("Use either --month or --start-date/--end-date, not both")
        sys.exit(1)
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            start_date, end_date = month_range(year, month)
        except Exception:
            print("Invalid --month, use YYYY-MM")
            sys.exit(1)
    else:
        if args.start_date and args.end_date:
            start_date, end_date = args.start_date, args.end_date
        else:
            now = datetime.now()
            start_date, end_date = month_range(now.year, now.month)

    prefix = args.prefix or "fasttoggl"
    clients = args.client_ids
    name_map = client.get_workspace_clients_map(args.workspace_id)
    try:
        # generate one file per client
        for cid in clients:
            client_label = _safe_name(name_map.get(cid, str(cid)))
            output = (
                args.output or f"./{prefix}_{client_label}_{start_date}_{end_date}.pdf"
            )
            client.download_detailed_report_pdf(
                workspace_id=args.workspace_id,
                client_ids=[cid],
                start_date=start_date,
                end_date=end_date,
                output_file=output,
            )
            print(output)
    except Exception as e:
        print(f"Error downloading report: {e}")
        sys.exit(1)


def toggl_fast_report_pdf(args):
    client = get_authenticated_client()
    if client is None:
        sys.exit(1)
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            start_date, end_date = month_range(year, month)
        except Exception:
            print("Invalid --month, use YYYY-MM")
            sys.exit(1)
    else:
        now = datetime.now()
        start_date, end_date = month_range(now.year, now.month)
    workspace_id = args.workspace_id
    if workspace_id is None:
        try:
            workspaces = client.get_workspaces()
            if not workspaces:
                print("No workspaces available")
                sys.exit(1)
            workspace_id = workspaces[0].id
        except Exception as e:
            print(f"Error loading workspaces: {e}")
            sys.exit(1)
    try:
        client_ids = client.get_clients_with_user_hours(
            workspace_id=workspace_id, start_date=start_date, end_date=end_date
        )
        if not client_ids:
            print("")
            return
        prefix = args.prefix or "fasttoggl"
        name_map = client.get_workspace_clients_map(workspace_id)
        for cid in client_ids:
            client_label = _safe_name(name_map.get(cid, str(cid)))
            output = f"./{prefix}_{client_label}_{start_date}_{end_date}.pdf"
            client.download_detailed_report_pdf(
                workspace_id=workspace_id,
                client_ids=[cid],
                start_date=start_date,
                end_date=end_date,
                output_file=output,
            )
            print(output)
    except Exception as e:
        print(f"Error downloading report: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="fasttoggl CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")
    prompt_parser = subparsers.add_parser("prompt", help="Edit system prompt")

    def _edit_prompt(_args):
        cm = CredentialsManager()
        os.makedirs(cm.config_dir, exist_ok=True)
        prompt_path = os.path.join(cm.config_dir, "system_prompt.txt")
        if not os.path.exists(prompt_path):
            with open(prompt_path, "w") as f:
                f.write(SYSTEM_INSTRUCTION)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        exit_code = os.system(f"{editor} {prompt_path}")
        if exit_code != 0:
            print(f"Editor exited with code {exit_code}")
            sys.exit(1)
        print(f"System prompt saved at: {prompt_path}")

    prompt_parser.set_defaults(func=_edit_prompt)

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_sub = auth_parser.add_subparsers(dest="auth_cmd")
    auth_setup = auth_sub.add_parser("setup", help="Configure Toggl credentials")
    auth_setup.set_defaults(func=lambda _args: setup_credentials())

    audio_parser = subparsers.add_parser("audio", help="Audio commands")
    audio_parser.add_argument(
        "-o",
        "--output",
        help="Output .wav file (optional)",
    )
    audio_parser.add_argument(
        "-i",
        "--input",
        help="Input .wav file (instead of recording)",
    )
    audio_parser.add_argument(
        "-d",
        "--duration",
        type=float,
        help="Recording duration in seconds (optional)",
    )
    audio_parser.add_argument(
        "-r",
        "--sample-rate",
        type=int,
        default=44100,
        help="Sample rate in Hz (default: 44100)",
    )
    audio_parser.add_argument(
        "-c",
        "--channels",
        type=int,
        default=1,
        choices=[1, 2],
        help="Number of channels (default: 1)",
    )
    audio_parser.add_argument(
        "--chunk-size",
        type=int,
        default=1024,
        help="Chunk size (default: 1024)",
    )
    audio_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Do not process audio with LLM",
    )
    audio_parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash",
        help="LLM model (default: gemini-2.5-flash)",
    )
    audio_parser.set_defaults(func=cmd_audio)

    toggl_parser = subparsers.add_parser("toggl", help="Operations in Toggl")
    toggl_sub = toggl_parser.add_subparsers(dest="toggl_cmd")
    toggl_parser.set_defaults(func=lambda _args: toggl_parser.print_help())

    toggl_orgs_cmd = toggl_sub.add_parser("orgs", help="List organizations")
    toggl_orgs_cmd.set_defaults(func=toggl_orgs)

    toggl_ws_cmd = toggl_sub.add_parser("workspaces", help="List workspaces")
    toggl_ws_cmd.set_defaults(func=toggl_workspaces)

    toggl_proj_cmd = toggl_sub.add_parser("projects", help="List projects")
    toggl_proj_cmd.add_argument("--workspace-id", type=int)
    toggl_proj_cmd.set_defaults(func=toggl_projects)

    toggl_te_cmd = toggl_sub.add_parser("time-entries", help="List time entries")
    toggl_te_cmd.add_argument("--since", type=int)
    toggl_te_cmd.add_argument("--before", type=str)
    toggl_te_cmd.add_argument("--start-date", type=str)
    toggl_te_cmd.add_argument("--end-date", type=str)
    toggl_te_cmd.add_argument("--limit", type=int)
    toggl_te_cmd.set_defaults(func=toggl_time_entries)

    toggl_create_proj_cmd = toggl_sub.add_parser(
        "create-project", help="Create project"
    )
    toggl_create_proj_cmd.add_argument("--workspace-id", type=int, required=True)
    toggl_create_proj_cmd.add_argument("--name", type=str, required=True)
    toggl_create_proj_cmd.set_defaults(func=toggl_create_project)

    toggl_create_te_cmd = toggl_sub.add_parser(
        "create-time-entry", help="Create time entry"
    )
    toggl_create_te_cmd.add_argument("--project-id", type=int, required=True)
    toggl_create_te_cmd.add_argument("--start", type=str, required=True)
    toggl_create_te_cmd.add_argument("--end", type=str, required=True)
    toggl_create_te_cmd.add_argument("--description", type=str, required=True)
    toggl_create_te_cmd.add_argument("--date", type=str)
    toggl_create_te_cmd.set_defaults(func=toggl_create_time_entry)

    toggl_report_pdf_cmd = toggl_sub.add_parser(
        "report-pdf", help="Download detailed report PDF from Reports API"
    )
    toggl_report_pdf_cmd.add_argument("--workspace-id", type=int, required=True)
    toggl_report_pdf_cmd.add_argument(
        "--client-ids", type=int, nargs="+", required=True
    )
    toggl_report_pdf_cmd.add_argument("--month", type=str)
    toggl_report_pdf_cmd.add_argument("--start-date", type=str)
    toggl_report_pdf_cmd.add_argument("--end-date", type=str)
    toggl_report_pdf_cmd.add_argument("--output", type=str)
    toggl_report_pdf_cmd.add_argument("--prefix", type=str)
    toggl_report_pdf_cmd.set_defaults(func=toggl_report_pdf)

    toggl_fast_report_pdf_cmd = toggl_sub.add_parser(
        "fast-report-pdf",
        help="Download detailed report PDF for each client with hours (month defaults to current)",
    )
    toggl_fast_report_pdf_cmd.add_argument("--workspace-id", type=int)
    toggl_fast_report_pdf_cmd.add_argument("--month", type=str)
    toggl_fast_report_pdf_cmd.add_argument("--prefix", type=str)
    toggl_fast_report_pdf_cmd.set_defaults(func=toggl_fast_report_pdf)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
