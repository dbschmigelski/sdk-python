from .use_github import use_github
from .find_issues_prompt import FIND_ISSUES_PROMPT
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from typing import Annotated
from pydantic import BaseModel, Field, HttpUrl


class Issue(BaseModel):
    """Represents a basic GitHub issue for review."""

    number: int = Field(..., description="Issue number")
    title: str = Field(..., description="Issue title")
    url: HttpUrl = Field(..., description="Full GitHub URL to the issue")
    labels: list[str] = Field(default_factory=list, description="All labels on the issue")
    created_at: str = Field(..., description="ISO date string when issue was created")
    reason_selected: str = Field(..., description="One sentence explanation of why this issue was selected for review")


class FindIssuesWrapper:
    def __init__(self):
        self.agent = Agent(
            model = BedrockModel(
            additional_request_fields={
                "anthropic_beta": ["context-1m-2025-08-07"]
            }),
            name="IssueFinderAgent", tools=[use_github], 
            system_prompt=FIND_ISSUES_PROMPT
        )

    @tool
    def find_issues(
        self, n: Annotated[int, "Maximum number of issues to return"] = 10
    ):
        """Find unprioritized issues from the GitHub repository for review."""
        prompt = f"""
        Find the top {n} MOST INTERESTING unprioritized issues from the strands-agents/sdk-python repository for review.
        
        CRITICAL SEARCH STRATEGY: To find the top {n} most interesting issues, you MUST:
        1. Fetch MANY MORE than {n} issues initially (recommend 3-5x more, so {n * 3}-{n * 5} issues)
        2. Filter out ALL issues with priority labels (High, Medium-High, Medium, Low)
        3. Score and rank the remaining unprioritized issues by engagement and importance
        4. Select only the top {n} highest-scoring issues
        
        FILTERING REQUIREMENTS:
        - ZERO priority labels allowed in results
        - Exclude ANY issue with priority labels: High, Medium-High, Medium, Low, or variations
        
        SCORING CRITERIA (apply to unprioritized issues only):
        - High reactions (5+): +5 points
        - Medium reactions (2-4): +3 points  
        - High comments (10+): +3 points
        - Bug label: +2 points
        - Feature label: +1 point
        - Then give 1-5 points based on initial impression of impact
        
        Return a list of Issue objects with fields: number, title, url, labels, created_at, reason_selected.
        Each reason_selected should explain why this unprioritized issue was chosen for review.
        """

        response = self.agent(prompt)
        print(response)

        # Parse the response and convert to Issue objects
        # The agent should return structured data following the SOP
        return response
