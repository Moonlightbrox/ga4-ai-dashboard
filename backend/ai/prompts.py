# This module stores the prompt text and labels used by the AI layer.
# It keeps system rules and button templates consistent across the app.

# ============================================================================
# Core System Prompts and Labels
# ============================================================================
# These constants define the system role, labels, and rules for AI responses.

SYSTEM_ROLE_PROMPT = (                                                       # Sets the AI's role and tone
    "SYSTEM ROLE:\n"
    "You are a data-grounded analytics assistant."
)

AGENT_SYSTEM_PROMPT = (                                                      # System prompt for the SQL agent
    "SYSTEM ROLE:\n"
    "You are a data-grounded analytics assistant for Google Analytics reports.\n"
    "\n"
    "ABSOLUTE RULES:\n"
    "- Use SQL tools for all calculations, aggregations, comparisons, and trends.\n"
    "- Do not guess or infer results.\n"
    "- If required instructions or fields are missing, stop and ask for them.\n"
    "\n"
    "INPUTS YOU RECEIVE:\n"
    "- A report table and column definitions.\n"
    "- SQL exploration and transformation tools.\n"
    "- A structured user instruction (button-generated).\n"
    "\n"
    "WORKFLOW (IN ORDER):\n"
    "1) Explore with SQL to understand structure and data quality.\n"
    "2) If multiple queries are needed and independent, batch them in a single tool call response.\n"
    "3) Run SQL that answers the instruction.\n"
    "3) Summarize findings in plain language.\n"
    "\n"
    "OUTPUT RULES:\n"
    "- Be concise and business-friendly.\n"
    "- Do not show raw SQL, UUIDs, or system details.\n"
    "- Say \"I don't know yet\" when exploration is insufficient.\n"
)
REPORT_CONTEXT_LABEL = "REPORT CONTEXT (JSON):"                              # Label that introduces report data in prompts
USER_QUESTION_LABEL = "USER QUESTION:"                                      # Label that introduces the user's question


# ============================================================================
# Button Prompt Templates
# ============================================================================
# These templates power prebuilt AI questions in the UI.

BUTTON_PROMPTS = {                                                          # Map of button IDs to detailed prompt text
    "traffic_quality_assessment": (
        "Analyze traffic source performance using engagement metrics (bounce rate, time on site, pages per session) and conversion metrics. Calculate quality score for each source based on multiple factors. Identify: (1) Sources with high volume but poor engagement/conversion (bot risk or poor targeting), (2) Sources with low volume but high quality (scaling opportunity), (3) Anomalous patterns. Output source-level metrics, quality ranking, and estimated wasted spend on low-quality traffic. Data QA: Flag sources with >80% bounce rate AND <10 second avg session (likely bots), sources with 0% conversion but high volume (tracking issue), or sudden traffic spikes >300% without corresponding revenue increase (suspicious traffic). Check for referrer spam patterns. Do NOT: recommend specific ad platforms without cost/CAC data, attribute quality issues to creative without creative performance data, or estimate fraud levels without bot detection data."
    ),
    "conversion_funnel_leakage": (
        "Using ecommerce_funnel report, calculate conversion rates between sequential funnel stages. Standard funnel: item_view â†’ add_to_cart â†’ begin_checkout â†’ purchase. Calculate: (1) Stage-to-stage conversion rates (add_to_cart/item_view, begin_checkout/add_to_cart, purchase/begin_checkout), (2) Overall funnel conversion (purchase/item_view), (3) Identify stage with largest drop-off, (4) If date dimension exists, identify if drop-off is worsening/improving over time. Output exact conversion percentages and loss magnitude at each stage. DATA QA: Flag if later funnel stages have higher counts than earlier stages (tracking error - purchases > item_views impossible), if any stage shows exactly 0 events for >7 consecutive days (tracking breakage), or if conversion rates are 100% at any stage (unrealistic). Verify funnel stages are mutually exclusive and properly sequenced. STRICT RULES: Use ONLY funnel stages present in ecommerce_funnel report. Do NOT invent additional micro-steps. Do NOT estimate reasons for drop-off without user behavior data. ALLOWED: Impact modeling (e.g., 'improving checkoutâ†’purchase by 10% would yield X additional purchases'), time-based trend analysis if date field exists. FORBIDDEN: Specific UX/design recommendations, assumptions about user psychology, checkout process details not in data, A/B test suggestions without test data."
    ),
    "landing_page_optimization": (
        "## Revenue: Top 5 Pages\n"
        "REVENUE BLOCK ONLY. Goal: show the top 5 most revenue-performing landing pages.\n"
        "Rules: rank by total Purchase Revenue (descending).\n"
        "Output: three small tables.\n"
        "Top Revenue Pages: Landing Page, Total Users, Purchase Revenue, Revenue per User, Session Length, Sessions per User, Conversion Rate, Bounce Rate.\n"
        "Top Total Users: Landing Page, Total Users, Purchase Revenue, Revenue per User, Session Length, Sessions per User, Conversion Rate, Bounce Rate.\n"
        "Top Revenue per User: Landing Page, Total Users, Purchase Revenue, Revenue per User, Session Length, Sessions per User, Conversion Rate, Bounce Rate.\n"
        "Then add two sections with headings:\n"
        "## Insights\n"
        "Give bullet points. Keep language short and concrete. each on a new line\n"
        "## Recommendations\n"
        "Give bullet points. Each recommendation must be supported by the metrics shown. Avoid generic advice. each on an new line\n"
        "Call out any pages with low users or sessions but unusually high revenue per user.\n"
        "When interpreting high/low metrics, acknowledge multiple plausible explanations and avoid assuming a single cause.\n"
        "If '(not set)' appears, call it out as untracked/unknown.\n"
        "Recommend what qeueres would you run next and why to get better recommendations."
        "Do not add extra sections."

    ),
}
