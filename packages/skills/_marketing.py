"""Marketing skills."""

from __future__ import annotations

MARKETING_SKILLS: list[dict] = [
    {
        "name": "campaign_brief",
        "description": "Marketing campaign brief: objective, audience, message, channels, KPIs, budget allocation.",
        "triggers": [
            "campaign brief", "marketing campaign", "campaign plan", "go-to-market", "GTM",
            "launch plan", "marketing brief", "campaign strategy",
        ],
        "preferred_tools": ["write_docx", "search_web", "email_composer", "read_kb", "write_kb"],
        "preferred_agents": ["marketing_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["marketing", "campaigns", "strategy"],
        "body": """\
## Campaign Brief Protocol

**Structure every campaign brief with:**

**1. Objective:**
- One primary goal (awareness / consideration / conversion / retention).
- Measurable target: "Increase trial sign-ups by 20% in Q3."

**2. Audience:**
- Primary segment: demographics, firmographics (B2B), psychographics.
- Jobs to be done: what are they trying to achieve?
- Channel preferences: where do they spend time?

**3. Key Message:**
- Single overarching message (one sentence).
- 3 supporting proof points.
- Tone: formal / conversational / urgent / inspirational.

**4. Channel Mix:**
- Paid: search, social, display, programmatic.
- Owned: email, blog, in-app, social.
- Earned: PR, partnerships, referrals.
- Assign % of budget and expected contribution per channel.

**5. Creative Requirements:**
- Formats needed: copy, imagery, video, landing page.
- Brand guidelines references.
- Legal/compliance review required? (yes/no + owner).

**6. KPIs & Measurement:**
- Primary KPI (the one metric that defines success).
- Secondary KPIs (reach, engagement, CAC, ROI).
- Attribution model: last-click / multi-touch / view-through.
- Reporting cadence.

**7. Budget:**
- Total budget.
- Breakdown by channel.
- Contingency reserve (typically 10–15%).

**8. Timeline:**
- Creative briefing → production → review → launch → campaign close → results report.

**Document via `write_docx`.**
""",
    },
    {
        "name": "content_calendar",
        "description": "Editorial content calendar: themes, formats, channels, cadence, ownership.",
        "triggers": [
            "content calendar", "editorial calendar", "content plan", "blog schedule",
            "social media plan", "content strategy", "editorial plan",
        ],
        "preferred_tools": ["create_excel", "write_docx", "read_kb", "write_kb"],
        "preferred_agents": ["marketing_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["marketing", "content", "editorial"],
        "body": """\
## Content Calendar Protocol

**Step 1 — Content Strategy Alignment:**
- Map content to buyer journey stages: Awareness / Consideration / Decision.
- Align themes with company OKRs and campaign calendar.
- Identify 3–5 content pillars (e.g. product education, thought leadership, customer stories).

**Step 2 — Audience & Channel Mapping:**
- For each persona: preferred content format (blog, video, podcast, infographic).
- For each channel: content type, tone, optimal length, posting frequency.
  - LinkedIn: 2–3×/week, professional, 150–300 words or carousel.
  - Blog: 2–4×/month, SEO-optimised, 1000–2000 words.
  - Email: weekly/bi-weekly, personalised, clear CTA.
  - Twitter/X: 1×/day, concise, hashtags limited to 1–2.

**Step 3 — Build the Calendar (use `create_excel`):**
Columns: Date | Platform | Content Type | Title/Topic | Content Pillar | Audience | Status | Owner | Link | Notes

**Step 4 — Content Production Workflow:**
- Brief → Draft → Review → Approve → Schedule → Publish → Repurpose.
- Define SLAs: brief (Day 1) → draft (Day 5) → review (Day 7) → approve (Day 8) → publish (Day 10).

**Step 5 — Repurposing Matrix:**
- Long-form blog → social snippets → email excerpt → LinkedIn post → infographic.
- Video → transcript → blog post → audiogram.

**Step 6 — Performance Review:**
- Monthly: top/bottom performers by engagement and conversion.
- Quarterly: audit full calendar against goals, adjust themes.
""",
    },
    {
        "name": "seo_audit",
        "description": "SEO audit: on-page issues, keyword gaps, technical SEO, backlink profile, recommendations.",
        "triggers": [
            "SEO audit", "SEO", "search engine optimisation", "search engine optimization",
            "keywords", "keyword research", "meta tags", "page rank", "organic traffic",
            "backlinks", "SERP", "on-page SEO",
        ],
        "preferred_tools": ["search_web", "fetch_url", "write_docx", "read_kb", "write_kb"],
        "preferred_agents": ["marketing_agent"],
        "supported_modes": ["research", "review"],
        "tags": ["marketing", "SEO", "technical"],
        "body": """\
## SEO Audit Protocol

**Step 1 — Keyword Research:**
- Identify: head terms (high volume, high competition), long-tail (lower volume, lower competition, higher intent).
- Group keywords by: informational / navigational / commercial / transactional intent.
- Map keywords to existing pages. Identify gaps (no page ranks for this keyword).

**Step 2 — On-Page Analysis (per key page):**
Check:
- Title tag: 50–60 chars, contains primary keyword near the front.
- Meta description: 150–160 chars, compelling, includes keyword.
- H1: one per page, contains primary keyword.
- H2–H3: structured, contain secondary keywords.
- Content length: sufficient for the topic (typically 1000+ words for competitive terms).
- Internal links: at least 3 links to/from other relevant pages.
- Image alt text: descriptive and keyword-relevant.
- URL structure: short, hyphen-separated, includes keyword.

**Step 3 — Technical SEO:**
- Page speed: target < 3s load time (use `fetch_url` to check headers).
- Mobile-friendliness: responsive design.
- Crawlability: check robots.txt and sitemap.xml.
- HTTPS: all pages served over HTTPS.
- Canonical tags: no duplicate content issues.
- Core Web Vitals: LCP, FID, CLS.

**Step 4 — Backlink Profile:**
- Total referring domains, domain authority distribution.
- Toxic backlinks to disavow.
- Competitor backlink gap analysis.

**Step 5 — Report:**
- Priority matrix: Quick Wins (high impact, low effort) | Major Projects | Fill-ins | No-nos.
- Use `write_docx` for the final report.
- Include: current state scores, target state, action list with owner and timeline.
""",
    },
    {
        "name": "brand_guidelines",
        "description": "Brand guidelines document: voice, tone, visual identity, usage rules, examples.",
        "triggers": [
            "brand guidelines", "brand identity", "tone of voice", "brand standards",
            "style guide", "brand voice", "visual identity", "brand manual",
        ],
        "preferred_tools": ["write_docx", "read_file", "read_kb", "write_kb"],
        "preferred_agents": ["marketing_agent", "writing_agent"],
        "supported_modes": ["chat"],
        "tags": ["marketing", "brand", "identity"],
        "body": """\
## Brand Guidelines Protocol

**Structure every brand guidelines document with:**

**1. Brand Foundation:**
- Mission: why the company exists.
- Vision: what the world looks like if you succeed.
- Values: 3–5 core values with behavioural descriptions.
- Positioning statement: "For [audience] who [need], [Brand] is [category] that [benefit], unlike [alternative]."

**2. Brand Voice:**
- 3–4 voice attributes with: description, do examples, don't examples.
- Example: *Confident but not arrogant* — "We built the fastest engine." ✓ vs. "We're the best, obviously." ✗

**3. Tone of Voice:**
- Adjust tone by context: social (playful) / sales (assertive) / support (empathetic) / legal (formal).
- Grammar and style rules: Oxford comma (yes/no), sentence case vs. Title Case, numbers (spell out under 10 / use numerals for data).

**4. Messaging Hierarchy:**
- Tagline (1 phrase).
- Elevator pitch (2–3 sentences).
- Core value propositions (3 bullets).
- Proof points per value proposition.

**5. Visual Identity (reference only — link to design system):**
- Primary and secondary colour palette (hex codes).
- Typography: primary and secondary typefaces, use cases.
- Logo usage: clear space, minimum size, approved backgrounds.
- Photography/illustration style description.

**6. Usage Rules:**
- What requires brand team approval before use.
- Common mistakes to avoid.

**Document via `write_docx`. Store in KB via `write_kb`.**
""",
    },
]
