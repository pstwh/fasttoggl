import os
from typing import List, Optional

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from fasttoggl.core.config import get_llm
from fasttoggl.core.credentials import CredentialsManager

SYSTEM_INSTRUCTION = """
You are an expert in logging working hours.
You will receive an audio file describing the employee's workday.
Your goal is to create a list of activities performed during the workday.

Working hours are always between 09:00 and 18:00, with a break from 12:00 to 13:00.
There can only be work between 09:00-12:00 and 13:00-18:00. Do not allow overlapping time ranges.

Consider the project context provided by the user. A task's project must be one of the provided projects.
Try to infer the project based on the task description and the user's audio.
If a project does not exist, set missing_project to True and list the missing names in missing_projects.
If the user explained a new project should be created, set create_project to True and provide its name in project_name.

Target language for all natural language fields (like description and project_name) is: {target_language}.
Keep JSON keys exactly as defined by the schema.

 Rules:
 - Output must be strictly valid JSON. No markdown, code fences, or extra text.
 - Use 24h time format HH:MM with leading zeros.
 - Sort activities by start_time ascending.
 - Ensure activities do not overlap and stay within the allowed windows (09:00-12:00 and 13:00-18:00).
 - If an activity spans across the lunch break, split it into two separate activities.
 - If no new project should be created, set create_project to false and project_name to an empty string.
 - If all projects are found, set missing_project to false and missing_projects to an empty list.

 Refinement behavior across multiple runs:
 - The context may include previous outputs (e.g., a JSON object under "activities" from earlier attempts). Treat the most recent prior output as the baseline plan.
 - Unless the user explicitly says to "overwrite all" or "replace all", you must MERGE the new information with the baseline instead of replacing it.
 - When the new audio introduces activities for time ranges that intersect existing ones, update only those specific intervals:
   • Insert the new tasks into the correct time ranges.
   • Split existing tasks as needed to make room, keeping unchanged portions intact. Example: If baseline has 13:00-18:00 and new audio adds 14:00-15:00, the result should be 13:00-14:00 (original), 14:00-15:00 (new), 15:00-18:00 (original).
   • Preserve descriptions and projects for segments that remain unchanged.
 - If there is no audio attached and only context is provided, treat the run as a refinement step and adjust the baseline accordingly.
 - Recompute missing_project, missing_projects, create_project, and project_name based on the MERGED result.

Response format:
{format}
"""
HUMAN_TEMPLATE = "Considering the context: {context} and based on the audio file, create the list of activities performed during the workday."


class WorkClock(BaseModel):
    start_time: str = Field(
        description="Task start time during the workday, format (HH:MM)",
        pattern=r"^(?:[01]\\d|2[0-3]):[0-5]\\d$",
    )
    end_time: str = Field(
        description="Task end time during the workday, format (HH:MM)",
        pattern=r"^(?:[01]\\d|2[0-3]):[0-5]\\d$",
    )
    description: str = Field(
        description="Detailed, formal description of the work performed during the task.",
        min_length=10,
    )
    project: str = Field(description="Name of the project to which the task belongs")


class WorkClockAnswer(BaseModel):
    missing_project: bool = Field(
        description="Set to True if any referenced project was not found; otherwise False"
    )
    missing_projects: List[str] = Field(
        description="List of project names that were not found"
    )
    create_project: bool = Field(
        description="Set to True if a new project should be created based on the user's audio"
    )
    project_name: str = Field(description="Name of the project that should be created")
    activities: List[WorkClock] = Field(
        description="List of activities performed during the workday"
    )


def get_chain(
    context: Optional[str] = None,
    encoded_audio: Optional[str] = None,
    mime_type: Optional[str] = None,
    model: Optional[str] = None,
):
    cm = CredentialsManager()
    language = cm.load_language()
    prompt_path = os.path.join(cm.config_dir, "system_prompt.txt")
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r") as f:
                system_instruction = f.read()
            if not str(system_instruction).strip():
                system_instruction = SYSTEM_INSTRUCTION
        except Exception:
            system_instruction = SYSTEM_INSTRUCTION
    else:
        system_instruction = SYSTEM_INSTRUCTION
    human_template = HUMAN_TEMPLATE

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_instruction),
            (
                "human",
                [
                    {"type": "text", "text": human_template},
                    *(
                        [
                            {
                                "type": "media",
                                "data": "{encoded_audio}",
                                "mime_type": "{mime_type}",
                            }
                        ]
                        if encoded_audio and mime_type
                        else []
                    ),
                ],
            ),
        ]
    )
    llm = get_llm(model=model)
    parser = JsonOutputParser(pydantic_object=WorkClockAnswer)
    prompt = prompt.partial(format=parser.get_format_instructions())
    if context:
        prompt = prompt.partial(context=context)
    if encoded_audio and mime_type:
        prompt = prompt.partial(encoded_audio=encoded_audio, mime_type=mime_type)
    if language:
        prompt = prompt.partial(target_language=language)
    chain = prompt | llm | parser

    return chain
