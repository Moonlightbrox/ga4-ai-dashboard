# GA4 Analytics Insights Catalog

A brainstorm / reference of interesting behavioral patterns and insights that
can be extracted from GA4 BigQuery export data. Not a roadmap, not prioritized
— a menu to pull from when designing analyses, summary tables, or prompts.

Each entry lists:
- **Insight** — what the finding looks like
- **Needs** — what raw/aggregated data is required
- **Value** — why a client would care

Sections are grouped by theme, not importance.

---

## 1. User Journey & Flow

### Top session path archetypes
- **Insight**: "3 dominant session shapes drive 70% of conversions: (A) paid → PDP → cart, (B) organic → blog → 3+ PDPs → cart, (C) direct → home → category → bounce."
- **Needs**: session-level ordered event sequence (first N steps).
- **Value**: reveals how users actually buy vs. the designed funnel.

### Most common 3-step sequences
- **Insight**: "The sequence `page_view(category) → page_view(product) → add_to_cart` converts 4x better than any other 3-step chain."
- **Needs**: event triples per session.
- **Value**: concrete patterns to double down on.

### Page-transition probability graph
- **Insight**: "From product-detail pages, 62% of users go to another PDP, only 12% reach the cart."
- **Needs**: page-to-page transition counts.
- **Value**: identifies weak links in the navigation.

### Hub pages
- **Insight**: "Page X appears in 45% of converting journeys but only 18% of bounces."
- **Needs**: page frequency by session outcome.
- **Value**: pages worth protecting / promoting.

### Dead-end pages
- **Insight**: "Page Y is the last page in 80% of sessions that hit it; no onward navigation."
- **Needs**: exit rate per page.
- **Value**: candidates for redesign or redirect.

### Path length distribution
- **Insight**: "Conversions happen at median 7 pageviews; sessions under 3 never convert."
- **Needs**: event count per session.
- **Value**: threshold for engagement quality.

### Loop / re-entry detection
- **Insight**: "8% of sessions revisit the same PDP 3+ times — usually research-heavy, convert eventually."
- **Needs**: page repeat counts within session.
- **Value**: flags research behavior vs. confusion.

### Optimal / shortest observed path
- **Insight**: "Fastest conversion path is home → category → product → cart → purchase in 5 events."
- **Needs**: shortest converting sequences.
- **Value**: the platonic ideal to design toward.

### Cross-device journey stitching
- **Insight**: "23% of purchases span 2+ devices — phone research, desktop purchase."
- **Needs**: `user_id` linking across sessions.
- **Value**: validates multi-device strategy.

### Backtrack behavior
- **Insight**: "Users who return to category pages mid-session convert at 2x rate."
- **Needs**: directional page flow (A → B → A patterns).
- **Value**: comparison shopping signal.

---

## 2. Cohorts & Retention

### Weekly acquisition cohort retention matrix
- **Insight**: Classic cohort triangle — retention by acquisition week × weeks since.
- **Needs**: first-visit week per user + weekly activity flags.
- **Value**: baseline retention health.

### Cohort drift
- **Insight**: "Cohorts acquired after June retain 15% worse at week 4."
- **Needs**: cohort retention over time with trend comparison.
- **Value**: detects silent degradation.

### Cohort LTV curves
- **Insight**: "Q1 cohort LTV is $X at 90d; Q2 is $Y — diverging since campaign switch."
- **Needs**: revenue aggregated by cohort week.
- **Value**: ties acquisition strategy to actual value.

### Cohort × acquisition source
- **Insight**: "Users acquired via organic have 2.3x 30-day retention vs. paid search."
- **Needs**: cohort segmented by first-touch source.
- **Value**: exposes stickiness differences across channels.

### Days-to-first-purchase distribution
- **Insight**: "Median purchase happens on day 3; 20% are same-day; 10% wait >2 weeks."
- **Needs**: time delta between first visit and first purchase per user.
- **Value**: informs retargeting window.

### Reactivation patterns
- **Insight**: "Users dormant 30+ days returning today are almost all via email."
- **Needs**: inactive gap detection + returning session source.
- **Value**: validates retention channels.

### Sleeping-beauty users
- **Insight**: "4% of converters had their first visit 60+ days before purchase."
- **Needs**: long lookback window on user timelines.
- **Value**: justifies long-horizon attribution.

### Seasonal cohort effects
- **Insight**: "Holiday-season-acquired cohorts retain 40% worse than off-season."
- **Needs**: cohort × acquisition month segmentation.
- **Value**: contextualizes campaign-driven acquisitions.

---

## 3. Segmentation & Clustering

### RFM segments
- **Insight**: Classic Recency / Frequency / Monetary — "Champions," "At Risk," "Lost," etc.
- **Needs**: per-user last-visit, visit-count, revenue.
- **Value**: universally understood marketing segmentation.

### Behavioral clusters (unsupervised)
- **Insight**: "4 natural user clusters: browsers, researchers, deal-hunters, direct buyers."
- **Needs**: user-feature vector; simple quantile/rule-based clustering is enough to start.
- **Value**: rich personas grounded in real behavior.

### High-intent fingerprints
- **Insight**: "Sessions with ≥2 PDPs + ≥1 search in first 3 minutes convert at 22% vs. 3% baseline."
- **Needs**: labeled sessions with early-event features.
- **Value**: actionable real-time targeting signals.

### Power users
- **Insight**: "Top 5% of users (by session count) drive 38% of revenue."
- **Needs**: user-level engagement percentile.
- **Value**: justifies loyalty programs.

### One-and-done users
- **Insight**: "42% of users never return; their first session averages 1.2 pages."
- **Needs**: single-session user profile.
- **Value**: top of funnel quality metric.

### Time-of-day segments
- **Insight**: "Evening mobile users convert 60% less but spend more time; morning desktop users close fast."
- **Needs**: session hour + device + outcome.
- **Value**: informs scheduling of campaigns / content.

### Geographic outliers
- **Insight**: "Users from region X have 3x normal bounce rate — possibly broken localization."
- **Needs**: country/region × metric deviations.
- **Value**: detects silent localization / infra issues.

### Mobile-only vs desktop-only vs cross-device
- **Insight**: "Cross-device users spend 2.4x more than mobile-only."
- **Needs**: device history per `user_id`.
- **Value**: justifies cross-device UX investment.

### Premium-content consumer segment
- **Insight**: "Users who read 2+ blog posts convert 2.1x at first purchase."
- **Needs**: content-category consumption flags per user.
- **Value**: content marketing ROI link.

---

## 4. Attribution & Traffic

### First-touch vs last-touch comparison
- **Insight**: "Paid is 60% of last-touch credit but only 25% of first-touch."
- **Needs**: per-user first and converting source.
- **Value**: exposes overreliance on late-funnel channels.

### Multi-touch sequences
- **Insight**: "Top converting path: organic → paid_retarget → direct. 12% of all converted users follow it."
- **Needs**: ordered source sequence per user.
- **Value**: reveals channel synergies.

### Assist rate by channel
- **Insight**: "Email assists 30% of conversions but is last-touch in only 6%."
- **Needs**: assist frequency per channel.
- **Value**: prevents killing high-assist channels.

### Paid vs organic head-to-head (same source)
- **Insight**: "Paid Google converts at 3.1%, organic Google at 5.4% — organic visitors are higher intent."
- **Needs**: medium split within one source.
- **Value**: cost-efficiency reality check.

### Branded vs non-branded search
- **Insight**: "Branded search converts 6x better but grew 0% YoY; non-branded drives all growth."
- **Needs**: keyword / term classification (if available).
- **Value**: separates harvesting from acquisition.

### Campaign fatigue
- **Insight**: "Campaign X CVR drops 30% after week 3 of running."
- **Needs**: conversion rate by campaign week-of-life.
- **Value**: informs creative refresh cadence.

### Direct-traffic halo effect
- **Insight**: "Direct traffic spikes 2 days after each paid campaign launch."
- **Needs**: daily direct vs. paid correlation.
- **Value**: uncovers true paid ROI.

### Referral quality ranking
- **Insight**: "Referrer X sends 200 sessions/week at 8% CVR; referrer Y sends 2000 at 0.4%."
- **Needs**: per-referrer engagement metrics.
- **Value**: partner / PR prioritization.

### Dark / suspicious direct
- **Insight**: "40% of 'direct' traffic lands on deep pages with no search history — likely email or dark social."
- **Needs**: landing-page depth × no-referrer flag.
- **Value**: re-attributes hidden marketing.

### UTM hygiene audit
- **Insight**: "13 campaigns share 4 utm_source spellings; normalization would consolidate 18% of 'direct.'"
- **Needs**: source/medium value distribution.
- **Value**: one-time cleanup with outsized reporting impact.

---

## 5. Content & Engagement

### Content-to-conversion affinity
- **Insight**: "Blog category 'guides' consumers convert at 2.3x site average."
- **Needs**: content-category tagging + per-user consumption + outcome.
- **Value**: content marketing ROI.

### Scroll depth distribution per page type
- **Insight**: "PDPs: 70% of users scroll past 50%; category pages: only 22%."
- **Needs**: scroll events by page type.
- **Value**: above-fold / layout signals.

### Internal search behavior
- **Insight**: "Top 10 searches cover 34% of queries; 12% return zero results."
- **Needs**: `view_search_results` events with terms.
- **Value**: exposes content/catalog gaps.

### Read-then-buy patterns
- **Insight**: "Sessions that read blog-post X then buy happen 80 times/week — strong buy-driver."
- **Needs**: blog → PDP → purchase sequences.
- **Value**: content-commerce link.

### Time-on-page quality bands
- **Insight**: "Users with 30–120s on PDPs convert best; <30s and >10min both convert poorly."
- **Needs**: page dwell-time buckets.
- **Value**: quality vs. quantity of engagement.

### Video / media engagement
- **Insight**: "Users who watch >50% of product video are 3x more likely to purchase."
- **Needs**: `video_progress` events.
- **Value**: media ROI grounding.

### Session-extending vs session-terminating pages
- **Insight**: "Page X extends session by avg 3 more pages; page Y ends 60% of sessions."
- **Needs**: post-page behavior per page.
- **Value**: content-surface strength ranking.

### Content freshness effect
- **Insight**: "Articles published within 30d drive 5x engagement of older content."
- **Needs**: content publish date (if captured).
- **Value**: editorial cadence justification.

---

## 6. Conversion & Revenue

### Conversion-rate cube
- **Insight**: Multi-dimensional CVR by source × device × landing × segment.
- **Needs**: cross-tabbed session outcomes.
- **Value**: finds underperforming intersections.

### AOV distribution
- **Insight**: "Median order $48; 90th percentile $180; top 5% of orders drive 28% of revenue."
- **Needs**: purchase event revenue distribution.
- **Value**: identifies premium-order characteristics.

### Items frequently bought together
- **Insight**: Basket co-occurrence — "Product A + B appear together in 23% of baskets."
- **Needs**: UNNESTed items array per purchase.
- **Value**: cross-sell / merchandising.

### Viewed-together but not bought-together
- **Insight**: "Products C and D are often viewed in the same session but rarely purchased together — likely substitutes."
- **Needs**: PDP co-occurrence vs. purchase co-occurrence.
- **Value**: exposes decision pairs.

### First vs repeat purchase behavior
- **Insight**: "First purchases skew category X; repeat purchases shift toward Y."
- **Needs**: purchase sequence per user.
- **Value**: lifecycle product strategy.

### Cart-size → conversion curve
- **Insight**: "1-item carts convert at 18%, 3+-item carts at 42%."
- **Needs**: cart event with item count.
- **Value**: AOV-building tactics validated.

### Revenue concentration (Pareto)
- **Insight**: "Top 10% of users = 62% of revenue; top 10% of products = 48%."
- **Needs**: user/product revenue sorting.
- **Value**: where to focus defense and acquisition.

### Discount / promo dependence
- **Insight**: "78% of purchases include a coupon; CVR without promo is 1.2%, with is 6.4%."
- **Needs**: coupon flag on purchase events.
- **Value**: promo sustainability check.

### Bundle vs single-item buyers
- **Insight**: "Bundle buyers return at 2.1x rate of single-item first purchasers."
- **Needs**: basket composition segmentation.
- **Value**: bundle-promotion justification.

---

## 7. Friction & Drop-off

### Funnel stage drop-off with benchmarks
- **Insight**: "Cart-to-checkout drops 68% here vs. 45% industry benchmark."
- **Needs**: ecommerce funnel stage counts.
- **Value**: prioritizes where to invest UX effort.

### Multi-session funnel completion
- **Insight**: "30% of purchases span 2+ sessions; funnel conversion per-session understates true rate."
- **Needs**: user-level cross-session funnel.
- **Value**: stops double-counting / underestimating.

### Checkout-step friction
- **Insight**: "Shipping form has 2.1 event repeats per user — likely validation errors."
- **Needs**: repeat-event counts per checkout step.
- **Value**: form-specific pain point.

### Device-specific friction
- **Insight**: "Mobile checkout completion is 4x lower than desktop at step 3."
- **Needs**: funnel × device.
- **Value**: targeted mobile fixes.

### Rage / frustration signals
- **Insight**: "5% of sessions include 3+ clicks in <2 seconds on same element."
- **Needs**: rapid-repeat-click detection (if click events instrumented).
- **Value**: UX defect hotspots.

### Repeated zero-result searches
- **Insight**: "1,200 zero-result searches/week — top term 'return policy' (navigational failure)."
- **Needs**: search term + result count.
- **Value**: content / nav gap.

### Product-view → abandon pattern
- **Insight**: "Users who view 5+ products in one session abandon 80% of the time."
- **Needs**: PDP count per session × outcome.
- **Value**: overchoice / filter-fail signal.

### 404 / error pages
- **Insight**: "Page title 'Not Found' appears in 2.3% of sessions; entry source mostly stale email."
- **Needs**: page-title or error-event scanning.
- **Value**: broken-link cleanup prioritization.

---

## 8. Temporal & Seasonal

### Hour × day heatmap
- **Insight**: "Traffic peaks Tuesday 2pm; conversion peaks Sunday 8pm — offset of 5 days."
- **Needs**: hour-of-day × day-of-week aggregation.
- **Value**: scheduling campaigns / inventory / support.

### Weekly seasonality
- **Insight**: "Weekend traffic is 2x weekday but CVR is half — browsing mode."
- **Needs**: day-of-week × metric.
- **Value**: correct benchmarking by day type.

### Week-over-week momentum
- **Insight**: "Sessions grew 8% WoW for 4 weeks; conversion rate flat — volume-driven growth."
- **Needs**: weekly metric trajectories.
- **Value**: growth-quality framing.

### Conversion lag distribution
- **Insight**: "Median days from first touch to conversion: 2.3; mode: same-day."
- **Needs**: user timestamp pairs.
- **Value**: attribution window sizing.

### Trend decomposition
- **Insight**: "Underlying trend is +1.5%/week; observed noise dominated by weekly seasonality."
- **Needs**: daily metric time series.
- **Value**: separates signal from seasonality.

### Event-driven spikes
- **Insight**: "Sessions jumped 300% on date X; likely press mention (referrer concentration)."
- **Needs**: anomaly detection + referrer diff.
- **Value**: attribution of surprise wins.

### Day-part performance drift
- **Insight**: "Morning CVR dropped 20% in past 3 weeks only; afternoon stable."
- **Needs**: day-part × week stability check.
- **Value**: localized regression detection.

---

## 9. Predictive / Leading Indicators

### Session-1 → conversion correlation
- **Insight**: "First-session users who view ≥2 categories are 3.2x more likely to convert within 7 days."
- **Needs**: first-session feature table + future-window label.
- **Value**: high-leverage targeting rules.

### Early-session conversion signal
- **Insight**: "Sessions with search + PDP in first 3 events convert at 18% vs. 2% baseline."
- **Needs**: first-N-events feature vector.
- **Value**: real-time personalization signal.

### Return-visit predictors
- **Insight**: "Users who scroll ≥75% on first visit return at 2x rate."
- **Needs**: first-visit engagement depth + 30d return flag.
- **Value**: onboarding quality targets.

### LTV early signals
- **Insight**: "Users who browse ≥3 categories in first week have 2.8x 90-day LTV."
- **Needs**: early-window behavior + future spend.
- **Value**: acquisition-quality scoring.

### At-risk early warning
- **Insight**: "Users whose session count drops 50% WoW are 4x more likely to churn next month."
- **Needs**: per-user weekly engagement trajectory.
- **Value**: proactive retention triggers.

### Conversion velocity
- **Insight**: "New users from source X convert in 1.2 days; source Y takes 11."
- **Needs**: time-to-convert per acquisition source.
- **Value**: cash-flow and attribution framing.

---

## 10. Anomaly & Change Detection

### Week-over-week metric shifts (>2σ)
- **Insight**: "Conversion rate on /checkout dropped 3.1σ below trend starting Oct 14."
- **Needs**: page × metric trend with confidence bands.
- **Value**: automated regression alarms.

### Source degradation
- **Insight**: "Source `partner_x` conversion dropped from 6% to 1.2% over 2 weeks."
- **Needs**: per-source conversion trend monitoring.
- **Value**: catches broken integrations fast.

### Device / browser breakages
- **Insight**: "Safari 17 bounce rate jumped to 78% from 42% — likely JS incompat."
- **Needs**: browser-version × metric drift.
- **Value**: regression root-cause hint.

### Landing-page shift after deploy
- **Insight**: "Landing page X bounce rate rose 30% the week of last deploy."
- **Needs**: page × metric before/after cut.
- **Value**: release-quality post-mortem.

### Traffic-composition drift
- **Insight**: "Paid share of traffic rose from 22% to 41% in 60 days; organic share fell."
- **Needs**: source-mix trend.
- **Value**: dependency / vulnerability tracking.

### Bot / spam heuristics
- **Insight**: "500 sessions/day from region X with zero-duration single-pageview pattern — probable bot."
- **Needs**: suspicious session fingerprint detection.
- **Value**: clean KPIs and spend.

### Sudden geo shift
- **Insight**: "Traffic from country Y tripled last week — no matching campaign, check for bot or PR."
- **Needs**: geo distribution delta.
- **Value**: early awareness of external events.

---

## 11. User Lifecycle

### Lifecycle stage distribution
- **Insight**: "30% discovering, 22% evaluating, 8% buying, 18% returning, 22% churning."
- **Needs**: per-user stage classification rules.
- **Value**: portfolio view of user base.

### Sessions-to-first-purchase distribution
- **Insight**: "Median 3 sessions to first purchase; 40% buy on session 1."
- **Needs**: session counter up to first purchase per user.
- **Value**: benchmarks nurture cadence.

### Return cadence
- **Insight**: "Top returning segment has median 4-day return cadence."
- **Needs**: inter-session gap distributions.
- **Value**: email/push timing.

### Post-purchase behavior
- **Insight**: "45% of first-purchasers return within 30d; 22% make second purchase."
- **Needs**: post-purchase timeline.
- **Value**: retention vs. one-time quality.

### Lifecycle transition rates
- **Insight**: "Evaluating-to-buying transition takes 2.1 days median; longer than 7d rarely converts."
- **Needs**: per-user stage transitions.
- **Value**: windows for intervention.

---

## 12. Ecommerce-specific

### PDP-view-to-add ratio by product
- **Insight**: "Product A: 18% PDP→cart; Product B: 2% — B is a view magnet but not a closer."
- **Needs**: per-product view vs. add counts.
- **Value**: merchandising prioritization.

### Product velocity
- **Insight**: "3 products rising >40% in view count WoW."
- **Needs**: per-product trend.
- **Value**: early demand signals.

### Category performance ranking
- **Insight**: Category by revenue, CVR, engagement — normalized.
- **Needs**: category-tagged product events.
- **Value**: resource allocation.

### Out-of-stock impact
- **Insight**: "Out-of-stock PDPs average 85% session-ending."
- **Needs**: stock/availability flag on PDP view.
- **Value**: inventory-UX link.

### Cross-sell effectiveness
- **Insight**: "Users shown 'recommended' then clicking it convert at 2.8x."
- **Needs**: recommendation impression + click events.
- **Value**: recommender ROI.

### Checkout payment-method mix
- **Insight**: "Users selecting payment X abandon 3x more than Y."
- **Needs**: payment-method selection events.
- **Value**: payment UX / provider decisions.

---

## 13. Data Quality / Health

### Tracking gaps
- **Insight**: "Days D1, D2 have 0 events — tracking outage."
- **Needs**: daily event counts.
- **Value**: prevents misreading of "drops."

### Schema drift
- **Insight**: "New `event_param.key` values appearing from date X — new instrumentation?"
- **Needs**: event-param key distribution over time.
- **Value**: QA and catalog sync.

### Duplicate events
- **Insight**: "2% of purchase events duplicate within 2 seconds — possible double-fire."
- **Needs**: near-timestamp dedupe per user.
- **Value**: revenue accuracy.

### user_pseudo_id stability
- **Insight**: "Avg sessions per `user_pseudo_id` dropped 30% — cookie / consent change?"
- **Needs**: user-session cardinality over time.
- **Value**: identity reliability tracking.

### Event-name taxonomy health
- **Insight**: "47 distinct event names; top 10 cover 98% — 37 are rare / likely stale."
- **Needs**: event distribution.
- **Value**: instrumentation hygiene.

---

## 14. Comparative / Benchmarking

### Period-over-period deltas
- **Insight**: "Last 30d vs. previous 30d: sessions +12%, CVR -4%, revenue +8%."
- **Needs**: rolling-window comparisons.
- **Value**: standard dashboard language.

### YoY (when data available)
- **Insight**: "YoY CVR up 18%, sessions flat — efficiency gain."
- **Needs**: ≥13 months of data.
- **Value**: contextualizes growth.

### Segment-vs-segment
- **Insight**: "Returning users: 6% CVR, 3.2 pages; new users: 1.8% CVR, 1.7 pages."
- **Needs**: side-by-side segment metrics.
- **Value**: makes differences concrete.

### Best-performing-segment reverse-engineering
- **Insight**: "Top-converting segment shares: mobile + evening + category A + from email."
- **Needs**: top-decile segment profiling.
- **Value**: lookalike targeting input.

---

## 15. Speculative / "AI-native" insights

These are harder and lean on pattern recognition more than tabulation. Worth
flagging as later-stage once the basics are solid.

### Narrative session summaries
- **Insight**: "A typical converting session looks like: arrives via email, visits 2 PDPs, adds, hesitates, returns 2 days later, purchases."
- **Needs**: session templating from clusters.
- **Value**: storytelling for non-technical stakeholders.

### Natural-language "what changed this week"
- **Insight**: "The biggest shift this week: mobile conversions on Android dropped sharply after Thursday, concentrated in one landing page."
- **Needs**: multi-dim anomaly attribution.
- **Value**: auto-generated exec summary.

### "If you could fix one thing" ranking
- **Insight**: "Largest estimated revenue lift from plausibly fixable friction: checkout-step-2 mobile (≈ $X/week)."
- **Needs**: impact-modeled drop-off estimation.
- **Value**: forces prioritization by value.

### Behavioral similarity search
- **Insight**: "Users who behaved like user U in their first week converted at 4x rate."
- **Needs**: user-feature vectors + similarity function.
- **Value**: lookalike without demographics.

### Causal-leaning hypotheses (with disclaimers)
- **Insight**: "After the homepage redesign, new-user bounce fell 11% while returning-user bounce unchanged — consistent with redesign helping discoverability."
- **Needs**: pre/post event × segment comparison.
- **Value**: frames possible causes without overclaiming.

---

## Notes on scope and honesty

- Not every insight above is achievable from GA4 export alone; some (e.g. rage
  clicks, video progress) require the site to instrument specific events.
- "Predictive" items in section 9 don't require ML — simple lift/correlation
  calculations on labeled first-session features are usually enough and far
  cheaper to explain.
- Anything described as "likely", "possibly", or "consistent with" is a
  hypothesis, not a conclusion. The data can support it; confirming causality
  needs experimentation outside GA4.
