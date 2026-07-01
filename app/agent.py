import datetime
import logging
import re
import sys
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.events import Event, RequestInput
from google.adk.models import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters, StdioConnectionParams
from google.adk.workflow import Workflow, node
from google.adk import Context
from google.genai import types

from app.config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("travel_planner")

# 1. MCP Toolset connection parameters
mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.mcp_server"],
        )
    )
)

# 2. Specialized Sub-Agents
flight_agent = LlmAgent(
    name="flight_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
    "You are a Flight Booking Expert.\n\n"

    "Always provide exactly THREE flight options.\n"
    "Use the search_flights tool.\n"

    "If the departure city is not provided, assume London Heathrow (LHR) "
    "and clearly state that it is an assumption.\n\n"

    "Each flight option must include:\n"
    "- Airline\n"
    "- Flight number\n"
    "- Departure airport\n"
    "- Arrival airport\n"
    "- Departure time\n"
    "- Arrival time\n"
    "- Duration\n"
    "- Price\n\n"

    "Never respond by asking for more information unless no assumption can reasonably be made."
    ),
    tools=[mcp_toolset],
)

hotel_agent = LlmAgent(
    name="hotel_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Hotel Expert. You search, compare, and recommend lodging options for the user. "
        "Use the search_hotels tool to look up available accommodations. "
        "Always return mock hotel options with names, ratings, amenities, and prices per night. "
        "Make sure the options align with the requested dates and destinations. "
        "Output a concise list of lodging options with details."
    ),
    tools=[mcp_toolset],
)

# 3. Agent Tools for Orchestrator delegation
flight_tool = AgentTool(agent=flight_agent)
hotel_tool = AgentTool(agent=hotel_agent)

# 4. Orchestrator Agent
orchestrator_agent = LlmAgent(
    name="orchestrator_agent",
    model=Gemini(
        model=config.model,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
    "You are the Head Travel Planner responsible for coordinating all travel planning.\n\n"

    "You MUST ALWAYS delegate flight-related tasks to flight_agent.\n"
    "You MUST ALWAYS delegate hotel-related tasks to hotel_agent.\n"
    "Do not answer these yourself if a specialized agent can do it.\n\n"

    "Workflow:\n"
    "1. Analyze the user's request.\n"
    "2. Call flight_agent to obtain flight recommendations.\n"
    "3. Call hotel_agent to obtain hotel recommendations.\n"
    "4. Use get_weather_forecast to retrieve weather information.\n"
    "5. Use calculate_travel_budget to estimate the total trip cost.\n"
    "6. Combine all results into one final itinerary.\n\n"

    "If any information is missing (such as departure city), make a reasonable assumption "
    "(for example, assume London Heathrow) and clearly mention the assumption instead of asking the user for more details.\n\n"

    "The final response must include:\n"
    "- Flight options\n"
    "- Hotel options\n"
    "- Weather forecast\n"
    "- Budget breakdown\n"
    "- Total estimated cost\n"
    "- Travel tips\n\n"

    "Only ask the user for more information if it is absolutely impossible to continue."
    ),
    tools=[flight_tool, hotel_tool, mcp_toolset],
)

# 4. Workflow Function Nodes
@node
async def security_checkpoint(ctx: Context, node_input: Any) -> Event:
    user_query = str(node_input)
    
    # PII scrubbing (passport number, credit card number, phone number)
    #passport_pattern = re.compile(r'\b[A-Z0-9]{6,9}\b', re.IGNORECASE)
    # Passport format: 1–2 letters followed by 6–8 digits
    passport_pattern = re.compile(
        r'\b[A-Z]{1,2}[0-9]{6,8}\b',
        re.IGNORECASE
    )
    cc_pattern = re.compile(r'\b(?:\d[ -]*?){13,16}\b')
    phone_pattern = re.compile(
        r'\+?\d{1,3}[-.\s]?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b'
    )
    
    scrubbed_query = user_query
    passport_matches = passport_pattern.findall(user_query)
    cc_matches = cc_pattern.findall(user_query)
    phone_matches = phone_pattern.findall(user_query)
    
    if passport_matches:
        scrubbed_query = passport_pattern.sub("[REDACTED_PASSPORT]", scrubbed_query)
    if cc_matches:
        scrubbed_query = cc_pattern.sub("[REDACTED_CARD]", scrubbed_query)
    if phone_matches:
        scrubbed_query = phone_pattern.sub("[REDACTED_PHONE]", scrubbed_query)
        
    ctx.state["user_query"] = scrubbed_query
    
    # Prompt injection keywords detection
    injection_keywords = ["ignore previous instructions", "system prompt", "bypass", "override", "you are now a"]
    detected_injection = any(kw in user_query.lower() for kw in injection_keywords)
    
    # Domain-specific rule: check for invalid/negative budget queries (prevent matching phone number hyphens)
    # Domain-specific rule: validate only the actual budget field
    negative_budget = False

    budget_match = re.search(
        r'budget\s*(?:is|:)?\s*(-?)\s*\$?\s*(\d+)',
        user_query,
        re.IGNORECASE,
    )

    if budget_match:
        sign = budget_match.group(1)
        amount = int(budget_match.group(2))

        if sign == "-" or amount <= 0:
            negative_budget = True

    # Optional: block obviously invalid requests
    if "free" in user_query.lower():
        negative_budget = True
            
    # Audit log
    audit_log = {
        "timestamp": str(datetime.datetime.now()),
        "pii_scrubbed": bool(passport_matches or cc_matches or phone_matches),
        "injection_detected": detected_injection,
        "negative_budget_rule_violated": negative_budget,
        "severity": "INFO"
    }
    
    import json

    if detected_injection:
        audit_log["severity"] = "CRITICAL"
        audit_log["reason"] = "Prompt injection attempt detected."
        logger.warning(json.dumps(audit_log))
        ctx.state["security_reason"] = "Potential prompt injection detected."
        return Event(output="Prompt injection detected.", route="SECURITY_EVENT")
        
    if negative_budget:
        audit_log["severity"] = "WARNING"
        audit_log["reason"] = "Invalid budget specified."
        logger.warning(json.dumps(audit_log))
        ctx.state["security_reason"] = "Travel plans must have a positive budget."
        return Event(output="Invalid budget.", route="SECURITY_EVENT")
        
    logger.info(json.dumps(audit_log))
    return Event(output=scrubbed_query, route="PROCEED")

# NOTE: rerun_on_resume=True is required here because this node dynamically
# schedules child agent runs (orchestrator_agent -> flight_agent / hotel_agent
# via AgentTool through ctx.run_node). The workflow can be interrupted right
# after this node (at human_approval_node's RequestInput) and later resumed
# (including via the NEEDS_REVIEW loop back into this same node). On resume,
# ADK needs to re-run this node to recover/regenerate the child agent
# response rather than assuming stale state, otherwise it raises:
# "A node must have rerun_on_resume=True. Reason is that dynamically
# scheduled nodes might be interrupted, and the workflow wakes-up/re-runs
# the parent node, so it can get the child node response."
@node(rerun_on_resume=True)
async def orchestrator_node(ctx: Context, node_input: Any) -> Event:
    query = ctx.state.get("user_query", str(node_input))
    res = await ctx.run_node(orchestrator_agent, query)
    
    plan_text = res.output if hasattr(res, "output") else str(res)
    ctx.state["current_plan"] = plan_text
    
    return Event(output=plan_text, route="PROCEED")

@node(rerun_on_resume=True)
def human_approval_node(ctx: Context, node_input: Any):
    # Check if we already received the feedback from an interrupt resume
    resume_input = ctx.resume_inputs.get("trip_feedback")
    
    if not resume_input:
        plan = ctx.state.get("current_plan", "No plan generated yet.")
        # Yield RequestInput to pause and wait for user review
        yield RequestInput(
            interrupt_id="trip_feedback",
            message=f"Please review the proposed travel plan:\n\n{plan}\n\nDo you approve this plan? (Reply 'yes/approve' to finalize, or describe any changes you want)."
        )
        return
        
    feedback_str = str(resume_input).strip()
    ctx.state["user_feedback"] = feedback_str
    
    if "yes" in feedback_str.lower() or "approve" in feedback_str.lower():
        plan = ctx.state.get("current_plan", "")
        return Event(output=plan, route="APPROVED")
    else:
        # Loop back: update query with feedback
        original_query = ctx.state.get("user_query", "")
        updated_query = f"Original Request: {original_query}\nUser feedback: {feedback_str}\nAdjust the plan accordingly."
        ctx.state["user_query"] = updated_query
        return Event(output=feedback_str, route="NEEDS_REVIEW")

@node
async def final_output_node(ctx: Context, node_input: Any) -> Event:
    plan = ctx.state.get("current_plan", "No plan generated.")
    return Event(output=f"Final Travel Itinerary (Confirmed):\n\n{plan}")

@node
async def security_event_node(ctx: Context, node_input: Any) -> Event:
    reason = ctx.state.get("security_reason", "Security policy violation.")
    return Event(output=f"ACCESS DENIED: {reason}")

# 5. Connect Workflow Graph
workflow = Workflow(
    name="travel_planner_workflow",
    edges=[
        ("START", security_checkpoint),
        (security_checkpoint, {
            "PROCEED": orchestrator_node,
            "SECURITY_EVENT": security_event_node,
        }),
        (orchestrator_node, human_approval_node),
        (human_approval_node, {
            "APPROVED": final_output_node,
            "NEEDS_REVIEW": orchestrator_node,
        }),
    ]
)

app = App(
    root_agent=workflow,
    name="app",
)