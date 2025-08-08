import base64
from datetime import datetime
from typing import List, Optional

import requests
from pydantic import BaseModel


class TogglWorkspace(BaseModel):
    id: int
    organization_id: int
    name: str


class TogglProject(BaseModel):
    id: int
    workspace_id: int
    name: str
    client_name: Optional[str] = None
    client_id: Optional[int] = None


class TogglOrganization(BaseModel):
    id: int
    name: str


class TogglTimeEntry(BaseModel):
    id: int
    description: Optional[str] = None
    start: Optional[str] = None
    stop: Optional[str] = None
    duration: Optional[int] = None
    pid: Optional[int] = None
    wid: Optional[int] = None


class TogglClientInterface:
    def get_workspaces(self) -> List[TogglWorkspace]:
        pass

    def get_projects(self) -> List[TogglProject]:
        pass

    def create_project(self, workspace_id: int, name: str) -> TogglProject:
        pass

    def put_hours(
        self, project: TogglProject, start: datetime, end: datetime, description: str
    ):
        pass


class TogglSessionClient(TogglClientInterface):
    def __init__(
        self,
        email: str,
        api_token: str,
        base_url: str = "https://track.toggl.com/api/v9",
    ):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        token = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("utf-8")
        self.session.headers.update(
            {
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        if not self._authenticate():
            raise Exception("Failed to authenticate")

    def _authenticate(self) -> bool:
        url = f"{self.base_url}/me"
        response = self.session.get(url)
        return response.status_code == 200

    def get_workspaces(self) -> List[TogglWorkspace]:
        url = f"{self.base_url}/me/workspaces"
        response = self.session.get(url)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")

        return [TogglWorkspace(**workspace) for workspace in response.json()]

    def get_organizations(self) -> List[TogglOrganization]:
        url = f"{self.base_url}/me/organizations"
        response = self.session.get(url)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
        return [TogglOrganization(**org) for org in response.json()]

    def create_project(self, workspace_id: int, name: str) -> TogglProject:
        URL = f"{self.base_url}/workspaces/{workspace_id}/projects"
        data = {
            "active": True,
            "cid": None,
            "color": "#c9806b",
            "is_private": True,
            "name": name,
            "wid": workspace_id,
            "start_date": datetime.now().strftime("%Y-%m-%d"),
            "end_date": None,
            "estimated_hours": None,
        }
        response = self.session.post(URL, json=data)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
            return None
        return TogglProject(**response.json())

    def get_projects(self, workspace_id: int) -> List[TogglProject]:
        URL = f"{self.base_url}/workspaces/{workspace_id}/projects"
        response = self.session.get(URL)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")

        return [TogglProject(**project) for project in response.json()]

    def get_project_client_map(self, workspace_id: int) -> dict[int, Optional[int]]:
        URL = f"{self.base_url}/workspaces/{workspace_id}/projects"
        response = self.session.get(URL)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
            return {}
        project_list = response.json() or []
        mapping: dict[int, Optional[int]] = {}
        for p in project_list:
            pid = p.get("id")
            cid = p.get("client_id")
            if cid is None:
                cid = p.get("cid")
            if isinstance(pid, int):
                mapping[pid] = cid if isinstance(cid, int) else None
        return mapping

    def get_workspace_clients_map(self, workspace_id: int) -> dict[int, str]:
        URL = f"{self.base_url}/workspaces/{workspace_id}/clients"
        response = self.session.get(URL)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
            return {}
        clients = response.json() or []
        return {
            c.get("id"): (c.get("name") or str(c.get("id")))
            for c in clients
            if isinstance(c.get("id"), int)
        }

    def get_clients_with_user_hours(
        self, workspace_id: int, start_date: str, end_date: str
    ) -> List[int]:
        entries = self.get_time_entries(start_date=start_date, end_date=end_date)
        project_to_client = self.get_project_client_map(workspace_id)
        client_ids: set[int] = set()
        for e in entries:
            try:
                if e.wid and e.wid != workspace_id:
                    continue
                if e.pid and e.pid in project_to_client:
                    cid = project_to_client.get(e.pid)
                    if cid:
                        client_ids.add(cid)
            except Exception:
                continue
        return sorted(client_ids)

    def get_all_projects(self) -> List[TogglProject]:
        URL = f"{self.base_url}/me/projects"
        response = self.session.get(URL)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
            return []
        return [TogglProject(**project) for project in response.json()]

    def get_time_entries(
        self,
        since: Optional[int] = None,
        before: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meta: Optional[bool] = None,
        include_sharing: Optional[bool] = None,
    ) -> List[TogglTimeEntry]:
        url = f"{self.base_url}/me/time_entries"
        params: dict = {}
        if since is not None:
            params["since"] = since
        if before is not None:
            params["before"] = before
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date
        if meta is not None:
            params["meta"] = str(meta).lower()
        if include_sharing is not None:
            params["include_sharing"] = str(include_sharing).lower()
        response = self.session.get(url, params=params)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code} 2")
            return []
        return [TogglTimeEntry(**entry) for entry in response.json()]

    def get_latest_time_entries(self, limit: int = 10) -> List[TogglTimeEntry]:
        entries = self.get_time_entries()
        try:
            sorted_entries = sorted(
                entries,
                key=lambda e: e.start or "",
                reverse=True,
            )
        except Exception:
            sorted_entries = entries
        return sorted_entries[:limit]

    def put_hours(
        self, project: TogglProject, start: datetime, end: datetime, description: str
    ):
        output_format = "%Y-%m-%dT%H:%M:%S.%fZ"

        start_formatted = start.strftime(output_format)
        end_formatted = end.strftime(output_format)

        duration_seconds = int((end - start).total_seconds())

        URL = f"{self.base_url}/time_entries"
        data = {
            "created_with": "fasttoggl",
            "pid": project.id,
            "tid": None,
            "description": description,
            "tags": [],
            "billable": False,
            "duration": duration_seconds,
            "groupBy": "",
            "wid": project.workspace_id,
            "start": start_formatted,
            "stop": end_formatted,
        }

        response = self.session.post(URL, json=data)
        if response.status_code != 200:
            print(f"ERROR, {response.status_code}")
            print(f"ERROR, {response.content}")
            raise Exception(f"Failed to create time entry: {response.status_code}")

    def download_detailed_report_pdf(
        self,
        workspace_id: int,
        client_ids: List[int],
        start_date: str,
        end_date: str,
        output_file: str,
        date_format: str = "YYYY-MM-DD",
        time_format: str = "HH:mm",
        duration_format: str = "improved",
        order_by: str = "date",
        order_dir: str = "desc",
        grouped: bool = False,
        collapse: bool = False,
        hide_amounts: bool = True,
        display_mode: str = "date_and_time",
    ) -> None:
        url = f"https://track.toggl.com/reports/api/v3/workspace/{workspace_id}/search/time_entries.pdf"
        payload = {
            "date_format": date_format,
            "duration_format": duration_format,
            "time_format": time_format,
            "client_ids": client_ids,
            "end_date": end_date,
            "start_date": start_date,
            "order_by": order_by,
            "order_dir": order_dir,
            "workspace_id": workspace_id,
            "grouped": grouped,
            "collapse": collapse,
            "hide_amounts": hide_amounts,
            "display_mode": display_mode,
        }
        headers = {
            "Accept": "application/pdf",
            "Content-Type": "application/json",
            "x-toggl-client": "fasttoggl",
        }
        response = self.session.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to download PDF: {response.status_code}")
        with open(output_file, "wb") as f:
            f.write(response.content)
