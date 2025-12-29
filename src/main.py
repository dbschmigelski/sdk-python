"""Main orchestrator for Community PR Review."""

from strands import Agent
from strands_tools import current_time
from strands.models.openai import OpenAIModel
from pydantic import BaseModel, Field
from .tools.find_issues import FindIssuesWrapper
from .tools.analyze_issue import AnalyzeIssueWrapper, IssueAnalysis
from .orchestrator_prompt import ORCHESTRATOR_PROMPT

# Configuration constants
DEFAULT_MAX_ISSUES = 12


class ReviewSummary(BaseModel):
    """Summary statistics for the review session."""

    total_issues: int = Field(..., description="Total number of issues reviewed")
    ready_for_contribution: int = Field(
        ..., description="Number of issues ready for contribution"
    )


class ReviewSession(BaseModel):
    """Complete review session output."""

    meeting_date: str = Field(..., description="Date of the review session (YYYY-MM-DD)")
    max_issues: int = Field(..., description="Maximum issues requested")
    focus_area: str | None = Field(None, description="Focus area if specified")
    summary: ReviewSummary = Field(..., description="Summary statistics")
    issues_analyzed: list[IssueAnalysis] = Field(
        default=[], description="Detailed analysis for each issue"
    )
    error_message: str | None = Field(None, description="Error message if session failed partially")


class CommunityPRReviewOrchestrator:
    """Orchestrates the community PR review process."""

    def __init__(self):
        # Initialize the sub-agents/tools
        self.find_issues_wrapper = FindIssuesWrapper()
        self.analyze_issue_tool = AnalyzeIssueWrapper().analyze_issue

        # Create the main orchestrator agent with the SOP as system prompt
        self.agent = Agent(
            tools=[
                self.find_issues_wrapper.find_issues,
                self.analyze_issue_tool,
                current_time,
            ],
            system_prompt=ORCHESTRATOR_PROMPT,
            model=OpenAIModel(model_id="gpt-5.2-2025-12-11")
            # model = BedrockModel(
            # additional_request_fields={
            #     "anthropic_beta": ["context-1m-2025-08-07"]
            # },
            # ),
        )

    def run_review(
        self, max_issues: int = 3, focus_area: str | None = None
    ) -> ReviewSession:
        """
        Run a community PR review session.

        Args:
            max_issues: Maximum number of issues to review
            focus_area: Optional focus area (e.g., "bugs", "tools", "features")

        Returns:
            ReviewSession with structured output
        """
        prompt = f"""
        Conduct a Community PR Review session with the following parameters:
        - max_issues: {max_issues}
        - focus_area: {focus_area or "None"}
        
        Use the current_time tool to get today's date for the meeting_date parameter.
        Follow the steps in your system prompt to complete the review session.
        
        Return a structured ReviewSession object with all required fields.
        """

        result = self.agent(prompt, structured_output_model=ReviewSession)
        return result.structured_output

    def generate_markdown(self, review: ReviewSession) -> str:
        """Generate markdown report from structured review data."""
        md = f"""# Community PR Review Session - {review.meeting_date}

## Session Summary
- **Total Issues Reviewed:** {review.summary.total_issues}
- **Ready for Contribution:** {review.summary.ready_for_contribution}
- **Max Issues Requested:** {review.max_issues}
- **Focus Area:** {review.focus_area or "All areas"}

"""
        
        # Handle error cases
        if review.error_message:
            md += f"""## Session Status: PARTIAL COMPLETION

**Error Encountered:** {review.error_message}

"""

        # Show analyzed issues
        if review.issues_analyzed:
            md += "## Issues Analyzed\n\n"
            for issue in review.issues_analyzed:
                md += f"""### Issue #{issue.issue_number}: {issue.issue_title}
**URL:** {issue.issue_url}
**Type:** {issue.issue_type}
**Recommended Priority:** {issue.recommended_priority}

**Summary:**
{" ".join(issue.summary) if issue.summary else "No summary available."}

**Priority Reasoning:**
{issue.priority_reasoning}

**Ready for Contribution:**
{"Yes" if issue.ready_for_contribution else "No"} - {issue.contribution_readiness_notes}

**Customer Impact:**
{"Yes" if issue.customer_impact else "No"}{f" - {issue.customer_impact_details}" if issue.customer_impact and issue.customer_impact_details else ""}
"""
                if issue.missing_information:
                    md += f"""
**Missing Information:**
{" ".join(issue.missing_information)}
"""

                md += "\n---\n\n"
        else:
            md += "## No Issues Analyzed\n\nNo issues were successfully analyzed during this session.\n\n"

        return md

    def run_and_save(
        self, max_issues: int = DEFAULT_MAX_ISSUES, focus_area: str | None = None
    ) -> str:
        """Run review and save to markdown file."""
        import os
        from datetime import datetime

        try:
            review = self.run_review(max_issues, focus_area)
            markdown = self.generate_markdown(review)
            meeting_date = review.meeting_date
        except Exception as e:
            # Fallback: create minimal report with error information
            meeting_date = datetime.now().strftime("%Y-%m-%d")
            markdown = f"""# Community PR Review Session - {meeting_date}

## Error During Review Session

The review session encountered an error and could not complete successfully.

**Error Details:**
{str(e)}

**Status:** INCOMPLETE - Please retry the review session

**Next Steps:**
1. Check GitHub API connectivity
2. Verify tool configurations
3. Retry the review session

---

*This is a fallback report generated due to system errors during the review process.*
"""
            print(f"Error during review session: {e}")

        # Ensure directory exists
        os.makedirs(".sop/reviews", exist_ok=True)

        # Write to file
        filepath = f".sop/reviews/community-pr-review-{meeting_date}.md"
        with open(filepath, "w") as f:
            f.write(markdown)

        return filepath


def main() -> None:
    """Run a community PR review session."""
    orchestrator = CommunityPRReviewOrchestrator()
    
    print("Starting Community PR Review Session...")
    print("=" * 60)

    filepath = orchestrator.run_and_save(
        max_issues=DEFAULT_MAX_ISSUES,
        focus_area=None,  # Review all areas
    )

    print("\n" + "=" * 60)
    print("Review Complete!")
    print(f"Review notes saved to: {filepath}")


if __name__ == "__main__":
    main()
