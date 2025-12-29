from .use_github import use_github
from .analyze_issue_prompt import ANALYZE_ISSUE_PROMPT
from strands import Agent, tool
from strands.models.bedrock import BedrockModel
from typing import Annotated, Literal
from pydantic import BaseModel, Field, HttpUrl


class IssueAnalysis(BaseModel):
    """Represents a comprehensive analysis of a GitHub issue."""

    issue_number: int = Field(..., description="Issue number")
    issue_title: str = Field(..., description="Issue title")
    issue_url: HttpUrl = Field(..., description="Full GitHub URL to the issue")
    issue_type: str = Field(
        ..., description="Issue type: bug, feature, tool, documentation, or other"
    )

    recommended_priority: Literal["High", "Medium-High", "Medium", "Low", "Close", "HUMAN_REVIEW_NEEDED"] = Field(
        ..., 
        description="Recommended priority level. High=IMMEDIATE on-call emergencies only, Medium-High=important bugs/features/reputation issues/paper-cuts, Medium=standard requests, Low=minor enhancements/breaking changes, Close=should be closed (duplicate/invalid/wontfix), HUMAN_REVIEW_NEEDED=too complex to assess"
    )
    priority_reasoning: str = Field(
        ..., description="Explanation for the priority recommendation"
    )
    current_labels: list[str] = Field(
        default_factory=list, description="List of existing labels"
    )

    ready_for_contribution: bool = Field(
        ..., description="Whether the issue is ready for community contribution"
    )
    contribution_readiness_notes: str = Field(
        ..., description="Explanation of contribution readiness assessment"
    )
    customer_impact: bool = Field(
        ..., description="Whether customer impact is mentioned"
    )
    customer_impact_details: str = Field(
        ..., description="Description of customer impact if present"
    )
    has_workaround: bool = Field(..., description="Whether a workaround is mentioned")
    security_concern: bool = Field(
        ..., description="Whether security implications exist"
    )
    linked_issues: list[int] = Field(
        default_factory=list, description="List of related issue/PR numbers"
    )
    summary: list[str] = Field(
        default_factory=list, description="Summary of what the issue is about"
    )
    missing_information: list[str] = Field(
        default_factory=list, description="List of information gaps"
    )
    comments_count: int = Field(..., description="Number of comments on the issue")
    created_at: str = Field(..., description="ISO date string when issue was created")
    last_updated: str = Field(..., description="ISO date string when issue was last updated")


class AnalyzeIssueWrapper:
    def __init__(self):
        self.agent = Agent(
            model = BedrockModel(
            additional_request_fields={
                "anthropic_beta": ["context-1m-2025-08-07"]
            }),
            name="IssueAnalyzerAgent",
            tools=[use_github],
            system_prompt=ANALYZE_ISSUE_PROMPT,
        )

    @tool
    def analyze_issue(
        self, issue_url: Annotated[str, "Full GitHub URL to the issue to analyze"]
    ) -> IssueAnalysis:
        """
        Perform comprehensive analysis of a GitHub issue to determine priority, labels, and contribution readiness.
        
        This tool conducts deep analysis of a single GitHub issue by:
        - Fetching complete issue details, comments, and metadata from GitHub API
        - Analyzing content for customer impact, security concerns, and technical complexity
        - Assessing priority based on severity, user impact, and availability of workarounds
        - Evaluating readiness for community contribution based on clarity and scope

        - Identifying patterns, missing information, and related issues
        
        Priority Assessment Guidelines (STRICTLY ENFORCED):
        - High: Reproducible bugs blocking core functionality with no workaround, system failures, data loss, security exploits, unhandled exceptions causing session termination, integration failures with major platforms (AWS Bedrock, etc.)
        - Medium-High: Important bugs affecting multiple users, significant features with clear demand, issues that make Strands look bad (deprecation warnings, sloppy errors), paper-cut labeled DevX issues
        - Medium: Standard feature requests, non-blocking bugs with workarounds, tool improvements, well-documented issues
        - Low: Minor enhancements, documentation updates, cosmetic issues, backwards compatibility breaking changes (unless critical)
        - Close: Issues that should be closed (duplicates, invalid requests, won't fix, out of scope, already resolved)
        
        Special Rules (CRITICAL):
        - HIGH PRIORITY RESERVED: Only for issues requiring IMMEDIATE on-call response or blocking essential workflows
        - Paper-cut labels INCREASE priority to Medium-High for DevX focus
        - Issues that "make Strands look bad" (poor UX, confusing errors) are Medium-High
        - Backwards compatibility breaking changes are LOW priority unless fixing critical bugs
        - Age affects community engagement but not inherent priority
        - Most issues should be "Medium" or "Low" - be conservative with higher priorities
        
        Use this tool when you need detailed analysis beyond basic issue information.
        The analysis includes technical assessment, business impact evaluation, and actionable recommendations.
        """
        prompt = f"""
        Analyze the following GitHub issue: {issue_url}
        
        Follow the steps in the SOP to:
        1. Fetch complete issue details from GitHub
        2. Extract context and impact information
        3. Assess priority indicators
        4. Evaluate contribution readiness
        5. Assess priority and contribution readiness
        6. Generate a comprehensive analysis summary
        
        Return a JSON object with all required fields populated according to the output format.
        """

        response = self.agent(prompt)
        print(response)

        # The agent should return structured JSON following the SOP
        return response
