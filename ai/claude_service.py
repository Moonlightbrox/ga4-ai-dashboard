"""
ai/claude_service.py
=====================================================================
Claude API integration with comprehensive report analysis
=====================================================================
"""

import os
import anthropic
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def business_health_check(reports: dict[str, pd.DataFrame], start_date: str, end_date: str) -> str:
    """
    Comprehensive business analysis using all core reports.
    
    Parameters:
    -----------
    reports : dict[str, pd.DataFrame]
        Dictionary of all core reports from get_all_core_reports()
    start_date : str
        Analysis start date
    end_date : str
        Analysis end date
    
    Returns:
    --------
    str : Formatted markdown analysis
    """
    
    # Prepare data context for Claude
    data_sections = []
    
    # Summary statistics
    traffic = reports.get("traffic_overview", pd.DataFrame())
    if not traffic.empty:
        total_users = traffic['totalUsers'].sum()
        total_sessions = traffic['sessions'].sum()
        total_revenue = traffic['purchaseRevenue'].sum()
        total_transactions = traffic['transactions'].sum()
        conv_rate = (total_transactions / total_users * 100) if total_users > 0 else 0
        
        data_sections.append(f"""**OVERALL METRICS ({start_date} to {end_date}):**
- Total Users: {total_users:,.0f}
- Total Sessions: {total_sessions:,.0f}
- Total Revenue: ${total_revenue:,.2f}
- Total Transactions: {total_transactions:,.0f}
- Conversion Rate: {conv_rate:.2f}%""")
    
    # Traffic Overview (top 20 rows)
    if not traffic.empty:
        data_sections.append(f"""
**TRAFFIC OVERVIEW (Top 20 by users):**
```csv
{traffic.nlargest(20, 'totalUsers').to_csv(index=False)}
```""")
    
    # Daily Trends (all data - important for trends)
    daily = reports.get("daily_trends", pd.DataFrame())
    if not daily.empty:
        data_sections.append(f"""
**DAILY TRENDS:**
```csv
{daily.to_csv(index=False)}
```""")
    
    # Landing Pages (top 15)
    landing = reports.get("landing_pages", pd.DataFrame())
    if not landing.empty:
        data_sections.append(f"""
**TOP LANDING PAGES (by sessions):**
```csv
{landing.nlargest(15, 'sessions').to_csv(index=False)}
```""")
    
    # User Acquisition (all data)
    acquisition = reports.get("user_acquisition", pd.DataFrame())
    if not acquisition.empty:
        data_sections.append(f"""
**USER ACQUISITION BY CHANNEL:**
```csv
{acquisition.to_csv(index=False)}
```""")
    
    # Ecommerce Funnel
    funnel = reports.get("ecommerce_funnel", pd.DataFrame())
    if not funnel.empty:
        data_sections.append(f"""
**ECOMMERCE FUNNEL:**
```csv
{funnel.to_csv(index=False)}
```""")
    
    # Geographic Performance (top 15)
    geo = reports.get("geographic_breakdown", pd.DataFrame())
    if not geo.empty:
        data_sections.append(f"""
**GEOGRAPHIC BREAKDOWN (Top 15 by revenue):**
```csv
{geo.nlargest(15, 'purchaseRevenue').to_csv(index=False)}
```""")
    
    # Combine all sections
    full_data = "\n\n".join(data_sections)
    
    prompt = f"""You are an expert business analyst reviewing Google Analytics data.

{full_data}

Provide a comprehensive business health check with this EXACT structure:

## 📊 Executive Summary
(3-4 sentences: overall health, key highlight, major concern, trajectory)

## 🚨 Critical Issues (Top 3)
For each issue:
- **Issue name**: Specific problem with numbers
- Impact: Why it matters
- Evidence: What data shows this

## 💡 Growth Opportunities (Top 3)  
For each opportunity:
- **Opportunity name**: Specific action with potential
- Potential: Expected impact
- Evidence: What data supports this

## 📈 Performance Analysis

### Traffic & Acquisition
- Best performing channels (with ROI if calculable)
- Underperforming channels
- Paid vs organic performance

### Conversion & Revenue
- Overall conversion trends
- Funnel bottlenecks (if ecommerce data exists)
- Revenue concentration

### Geography & Devices
- Top markets and untapped potential
- Device/browser optimization needs

## 🎯 Action Plan (Prioritized)
1. [Most urgent action with expected impact]
2. [Second priority]
3. [Third priority]
4. [Quick wins]
5. [Long-term initiatives]

## ⚠️ Confidence & Caveats
- What assumptions are you making?
- What data would improve this analysis?
- What should be monitored closely?

**IMPORTANT:**
- Be specific with numbers and percentages
- Compare segments (e.g., "Mobile converts at 0.8% vs desktop 1.5%")
- Calculate ROI where possible (revenue/users by channel)
- Identify concrete issues, not vague observations
- Every recommendation should be actionable"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return message.content[0].text


def chat_with_data(
    reports: dict[str, pd.DataFrame],
    user_question: str,
    conversation_history: list = None,
    start_date: str = None,
    end_date: str = None
) -> str:
    """
    Interactive chat with comprehensive GA4 data.
    
    Parameters:
    -----------
    reports : dict[str, pd.DataFrame]
        All core reports
    user_question : str
        User's question
    conversation_history : list, optional
        Previous messages for context
    start_date : str, optional
        Date range context
    end_date : str, optional
        Date range context
    
    Returns:
    --------
    str : Claude's response
    """
    
    # Build concise data context (sample data only for chat)
    data_sections = []
    
    date_context = f"**Date Range:** {start_date} to {end_date}\n\n" if start_date and end_date else ""
    
    # Include relevant data based on question keywords
    question_lower = user_question.lower()
    
    # Always include traffic overview
    traffic = reports.get("traffic_overview", pd.DataFrame())
    if not traffic.empty:
        data_sections.append(f"""**TRAFFIC OVERVIEW (sample):**
```csv
{traffic.head(30).to_csv(index=False)}
```""")
    
    # Add landing pages if question mentions pages/content
    if any(word in question_lower for word in ["page", "landing", "content", "blog", "url"]):
        landing = reports.get("landing_pages", pd.DataFrame())
        if not landing.empty:
            data_sections.append(f"""**LANDING PAGES:**
```csv
{landing.head(20).to_csv(index=False)}
```""")
    
    # Add trends if question mentions time/trend/growth
    if any(word in question_lower for word in ["trend", "time", "daily", "growth", "decline", "over"]):
        daily = reports.get("daily_trends", pd.DataFrame())
        if not daily.empty:
            data_sections.append(f"""**DAILY TRENDS:**
```csv
{daily.to_csv(index=False)}
```""")
    
    # Add funnel if question mentions conversion/funnel/cart
    if any(word in question_lower for word in ["conversion", "funnel", "cart", "checkout", "purchase"]):
        funnel = reports.get("ecommerce_funnel", pd.DataFrame())
        if not funnel.empty:
            data_sections.append(f"""**ECOMMERCE FUNNEL:**
```csv
{funnel.to_csv(index=False)}
```""")
    
    # Add products if question mentions product/item
    if any(word in question_lower for word in ["product", "item", "sell", "best seller"]):
        products = reports.get("top_products", pd.DataFrame())
        if not products.empty:
            data_sections.append(f"""**TOP PRODUCTS:**
```csv
{products.head(30).to_csv(index=False)}
```""")
    
    # Add device data if question mentions device/mobile/desktop
    if any(word in question_lower for word in ["device", "mobile", "desktop", "phone", "browser"]):
        device = reports.get("device_performance", pd.DataFrame())
        if not device.empty:
            data_sections.append(f"""**DEVICE PERFORMANCE:**
```csv
{device.to_csv(index=False)}
```""")
    
    # Add geographic data if question mentions country/location/geo
    if any(word in question_lower for word in ["country", "location", "geographic", "market", "region"]):
        geo = reports.get("geographic_breakdown", pd.DataFrame())
        if not geo.empty:
            data_sections.append(f"""**GEOGRAPHIC BREAKDOWN:**
```csv
{geo.head(30).to_csv(index=False)}
```""")
    
    full_data = "\n\n".join(data_sections)
    
    # Build messages
    messages = []
    
    # Add conversation history if exists
    if conversation_history:
        messages.extend(conversation_history)
    
    # Add current question with data context
    messages.append({
        "role": "user",
        "content": f"""You are analyzing Google Analytics data for a business.

{date_context}{full_data}

**User Question:** {user_question}

Provide specific, data-driven insights. Reference actual numbers from the data. Be concise but thorough. If you need to calculate metrics (like conversion rate, ROI, etc.), do the math and show it."""
    })
    
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=messages
    )
    
    return message.content[0].text


def quick_insights(reports: dict[str, pd.DataFrame]) -> dict:
    """
    Generate quick key insights for dashboard cards.
    
    Returns:
    --------
    dict : Key metrics and one-line insights
    """
    
    traffic = reports.get("traffic_overview", pd.DataFrame())
    if traffic.empty:
        return {
            "key_insight": "No data available",
            "critical_issue": "No data available",
            "opportunity": "No data available"
        }
    
    # Prepare minimal data
    traffic_summary = traffic.nlargest(15, 'totalUsers').to_csv(index=False)
    
    prompt = f"""Analyze this data and provide ONLY these three insights (each max 15 words):

Data:
```csv
{traffic_summary}
```

Respond in this EXACT JSON format with no other text:
{{
    "key_insight": "One key finding in 15 words or less",
    "critical_issue": "Most urgent problem in 15 words or less",
    "opportunity": "Biggest opportunity in 15 words or less"
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    # Parse JSON response
    import json
    try:
        response_text = message.content[0].text.strip()
        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        return json.loads(response_text.strip())
    except:
        return {
            "key_insight": message.content[0].text[:100],
            "critical_issue": "Parse error",
            "opportunity": "Parse error"
        }