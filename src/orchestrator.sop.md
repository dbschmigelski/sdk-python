# Community PR and Issue Review Meeting Facilitator

## Overview
This SOP guides the facilitation of Community PR and Issue Review meetings for the strands-agents repositories. The meeting provides visibility into community-reported bugs and pull requests, ensuring timely review and prioritization of issues impacting customers.

## Parameters
- **meeting_date** (required): The date of the review session (YYYY-MM-DD format)
- **max_issues** (optional, default: DEFAULT_MAX_ISSUES): Maximum number of issues to review in this session
- **backlog_url** (optional, default: "https://github.com/orgs/strands-agents/projects/4/views/7?sliceBy%5Bvalue%5D=_noValue&filterQuery=-status%3ACompleted+-is%3Apr+no%3Aparent-issue+no%3Apriority"): GitHub project board URL for backlog issues
- **focus_area** (optional): Specific area to focus on (e.g., "bugs", "tools", "features")

**Constraints for parameter acquisition:**
- You MUST ask for all required parameters upfront in a single prompt
- You MUST validate the meeting_date format
- You SHOULD ask if there are specific areas or issue types to prioritize

## Critical Error Handling Rule
**NEVER GENERATE MOCK DATA**: If GitHub API fails or is unavailable, the review session MUST be terminated with an error. Do NOT create fake issues, mock analysis, or proceed with fabricated information under any circumstances. Proper error handling preserves data integrity and prevents misleading results.

## Formatting Requirements
**NO BULLET POINTS**: All analysis output must use complete sentences and paragraph format. Avoid bullets, dashes, or list markers in findings, summaries, or recommendations. Write in flowing narrative style with maximum 3 key points per section.

## Steps

### 1. Session Setup and Preparation
Initialize the review session environment and gather necessary information.

**PERFORMANCE OPTIMIZATION:**
- Batch independent operations to improve efficiency

**Constraints:**
- You MUST create a review notes document at `.sop/reviews/community-pr-review-{meeting_date}.md`
- You MUST record the review date and parameters
- You MUST access the backlog board URL to retrieve current issues
- You MUST fetch up to max_issues from the backlog, prioritizing:
  - Issues with no priority assigned
  - Issues labeled as bugs
  - Issues in the specified focus_area (if provided)
- You SHOULD check for any urgent issues or patterns in recent submissions

### 2. Issue Analysis
Analyze each fetched issue to understand its context and impact.

**Constraints:**
- You MUST review each issue individually and thoroughly
- You MUST extract the following information for each issue:
  - Issue title and number
  - Issue description and context
  - Labels currently applied
  - Linked PRs or related issues
  - Customer impact (if mentioned)
  - Reproduction steps (for bugs)
  - Proposed solution (for features)
- You MUST document your analysis in the review notes
- You SHOULD identify patterns across multiple issues
- You SHOULD check for duplicate or related issues

### 3. Priority Assessment
Determine the appropriate priority level for each issue based on impact and urgency.

**Constraints:**
- You MUST assign a priority level to each issue from ONLY: High, Medium-High, Medium, Low
- CRITICAL: "High" priority is RESERVED for issues requiring IMMEDIATE on-call response
- You MUST apply the general guideline: Tools are normally no higher than "Medium" priority
- You MUST consider the following factors:
  - Customer impact and severity
  - Number of users affected
  - Availability of workarounds
  - Security implications
  - Blocking vs non-blocking nature
- For PRs, You MUST check linked issues for priorities and give more weight to issues marked as ready for contribution
- You MUST document your reasoning for each priority assignment
- You SHOULD identify any issues requiring immediate attention

### 4. Contribution Readiness Assessment
Evaluate each issue for community contribution readiness.

**Constraints:**
- You MUST evaluate each issue for "Ready for Contribution" based on:
  - Clear problem statement
  - Sufficient context for external contributors
  - Well-defined scope
  - No blocking dependencies
- You MUST document contribution readiness assessment in the review notes

**Priority Guidelines (STRICTLY ENFORCED):**
- **High**: IMMEDIATE on-call fixes ONLY - complete system failures, active data loss, critical security exploits, service outages
- **Medium-High**: Important features with clear customer demand, significant bugs affecting multiple users with complex workarounds
- **Medium**: Standard features, non-blocking bugs with workarounds, tool improvements, documentation for core features
- **Low**: Documentation updates, minor enhancements, cosmetic issues, nice-to-have features

**WARNING: Most issues should be Medium or Low. High priority means "wake up the on-call engineer."**

### 5. Summary and Insights
Create a comprehensive summary of the review session with actionable insights.

**Constraints:**
- You MUST create a summary table of all reviewed issues with:
  - Issue number and title
  - Assigned priority
  - Contribution readiness
  - Key findings (max 3 concise sentences, no bullets)
- You MUST identify patterns or recurring themes across issues
- You MUST highlight any critical issues requiring immediate attention
- You SHOULD provide recommendations for improving issue quality or documentation
- You SHOULD note any gaps in the codebase or documentation revealed by the issues
- You MUST save all review notes to `.sop/reviews/community-pr-review-{meeting_date}.md`

### 6. GitHub Issue Updates
Apply the determined priorities to the reviewed issues.

**Constraints:**
- You MUST update each reviewed issue with the assigned priority
- You MUST add "Ready for Contribution" label where recommended
- You SHOULD add a comment summarizing the review findings if it provides value to contributors
- You MUST verify all updates were applied successfully
- You MUST document any issues that couldn't be updated and why
- You SHOULD provide a final summary of all changes made

## Desired Outcome
- All fetched issues thoroughly analyzed and prioritized
- Clear priority levels assigned based on objective criteria
- Issues properly assessed for community contribution readiness
- Comprehensive review notes documenting analysis and decisions
- Patterns and insights identified for follow-up
- Improved visibility into community-reported issues
- GitHub issues updated with appropriate metadata

## Examples

### Example Input
```
meeting_date: "2024-12-09"
max_issues: DEFAULT_MAX_ISSUES
focus_area: "bugs"
```

### Example Process
1. Create review notes document
2. Fetch DEFAULT_MAX_ISSUES issues from backlog, prioritizing bugs without priority
3. Analyze each issue for context, impact, and requirements
4. Assign priority levels based on objective criteria
5. Assess contribution readiness for each issue
6. Create summary with patterns and insights
7. Update GitHub issues with priorities

### Example Output
```
Review Session: 2024-12-09 Community PR Review

Issues Reviewed: DEFAULT_MAX_ISSUES
- 8 bugs prioritized
- 4 feature requests evaluated
- 5 marked "Ready for Contribution"

Priority Distribution:
- High: 1 (cachePoint validation bug - customer blocking)
- Medium-High: 2 (MCP config support, conversation manager hooks)
- Medium: 6 (tool improvements, documentation updates)
- Medium-Low: 1 (structured output processing)
- Low: 2 (new database tools)

Key Patterns:
- Multiple requests for better MCP integration
- Caching features highly requested
- Tool-related issues consistently low priority

Recommendations:
- Consider MCP documentation improvements
- Follow up on Bedrock cachePoint bug with AWS team
- Create contribution guide for new tools
```

## Troubleshooting

### Unable to Access GitHub Board
If the backlog board URL is inaccessible:
- Verify the URL is correct and not expired
- Check GitHub authentication and permissions
- Ask team members to manually share issue numbers to review

### Ambiguous Issue Information
If an issue lacks sufficient information for proper assessment:
- Document what information is missing
- Add a comment to the issue requesting clarification
- Assign a tentative priority with a note about uncertainty
- Mark for follow-up review once information is provided

### Priority Assignment Uncertainty
If the appropriate priority level is unclear:
- Document the factors creating uncertainty
- Default to higher priority if customer impact is mentioned
- Add a note explaining the reasoning
- Flag for human review if the issue is potentially critical

### Rate Limiting or API Issues
If GitHub API rate limits are hit:
- Document which issues were successfully updated
- Save remaining updates to apply later
- Note the rate limit reset time
- Continue with review analysis even if updates can't be applied immediately

### GitHub API Service Unavailable
If GitHub API is completely unavailable after 3 retry attempts:
- Terminate the review session with an error after exhausting retries
- DO NOT generate mock data or fake analysis
- DO NOT proceed with fabricated issue information
- Document the service unavailability in the review notes
- Schedule a retry when services are restored

## Best Practices

### Issue Evaluation
- Consider customer impact first
- Look for patterns across multiple issues
- Check for duplicate or related issues
- Verify issue has enough information for contribution
- Be consistent in priority assignment across similar issues

### Analysis Quality
- Read the full issue description and all comments
- Check linked PRs and related issues
- Look for customer impact statements
- Consider the complexity of implementation
- Evaluate whether the issue is well-scoped

### Documentation
- Use consistent formatting in review notes
- Link to all reviewed issues
- Document reasoning for priority assignments
- Include context for future reference
- Highlight patterns and insights clearly

### Contribution Assessment
- Be conservative with "Ready for Contribution" label
- Ensure contribution readiness criteria are met
- Use consistent assessment across similar issues
- Add explanatory comments when readiness status might be unclear

## Artifacts
- `.sop/reviews/community-pr-review-{meeting_date}.md` - Complete review notes with analysis, decisions, and insights