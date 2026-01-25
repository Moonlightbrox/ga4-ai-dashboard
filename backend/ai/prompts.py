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

REPORT_CONTEXT_LABEL = "REPORT CONTEXT (JSON):"                              # Label that introduces report data in prompts
USER_QUESTION_LABEL = "USER QUESTION:"                                      # Label that introduces the user's question

ANALYSIS_RULES_PROMPT = (                                                    # Guardrails that limit what the AI can claim
    "RULES:\n"
    "You may only use the data provided in the reports.\n"
    "Do not assume missing data.\n"
    "Do not infer metrics that are not present.\n"
    "If the user asks a question that cannot be answered with the provided reports, respond exactly with:\n"
    "\"This question requires a report that is not currently included.\"\n"
    "Be concise, factual, and analytical."
)

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
        "You are given a table where each row represents a page and includes metrics such as Page, Revenue, Users, Sessions, and other numeric fields.\n"
        "\n"
        "Task:\n"
        "\n"
        "Identify the top 5 pages by Revenue.\n"
        "\n"
        "Rank pages from highest to lowest Revenue.\n"
        "\n"
        "Use only the data provided. Do not estimate or invent values.\n"
        "\n"
        "Output format:\n"
        "\n"
        "Page name - Revenue\n"
        "Page name - Revenue\n"
        "Page name - Revenue\n"
        "Page name - Revenue\n"
        "Page name - Revenue"
    ),
}

