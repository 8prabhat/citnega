"""UX and design skills."""

from __future__ import annotations

UX_SKILLS: list[dict] = [
    {
        "name": "design_critique",
        "description": "UX/UI design critique using Nielsen's heuristics: findings by severity, actionable recommendations.",
        "triggers": [
            "design critique", "design review", "UI review", "UX critique",
            "heuristic evaluation", "design feedback", "UX review", "usability review",
            "accessibility audit", "design assessment",
        ],
        "preferred_tools": ["read_file", "write_file", "fetch_url", "read_kb", "write_kb"],
        "preferred_agents": ["ux_design_agent"],
        "supported_modes": ["review", "chat"],
        "tags": ["ux", "design", "review"],
        "body": """\
## Design Critique Protocol (Nielsen's 10 Heuristics)

**Evaluation Framework — rate each heuristic: Pass / Minor Issue / Major Issue / Critical:**

1. **Visibility of System Status** — Does the UI always keep users informed? (loading states, progress, confirmations)
2. **Match Between System and Real World** — Does it use language users understand? No jargon, logical conventions.
3. **User Control and Freedom** — Can users undo, redo, and exit unwanted states easily?
4. **Consistency and Standards** — Consistent use of UI patterns, terminology, and conventions (platform-native).
5. **Error Prevention** — Does the design prevent errors before they happen? (confirmations, constraints, defaults)
6. **Recognition Rather Than Recall** — Are options visible? No need to memorise information between steps.
7. **Flexibility and Efficiency** — Does it support both novice and expert users? (shortcuts, personalization)
8. **Aesthetic and Minimalist Design** — No irrelevant information. Every element earns its place.
9. **Help Users Recognise, Diagnose, and Recover From Errors** — Error messages: plain language, describe problem, suggest solution.
10. **Help and Documentation** — When needed, is help easy to find and task-focused?

**Severity Rating:**
- **Critical (must fix before launch):** blocks core tasks or causes data loss.
- **High (fix this sprint):** significantly impacts task completion or causes confusion.
- **Medium (fix within 2 sprints):** noticeable friction, workarounds exist.
- **Low (backlog):** polish items, minor inconsistencies.

**For each finding, document:**
- Heuristic violated.
- Screen/component.
- Observed behaviour.
- Expected behaviour.
- Severity.
- Recommendation (specific, actionable).

**Accessibility Check (WCAG 2.1 AA):**
- Colour contrast ratio ≥ 4.5:1 for normal text, 3:1 for large text.
- All interactive elements keyboard-accessible.
- Focus indicators visible.
- Images have alt text.
- Form fields have labels.
""",
    },
    {
        "name": "wireframe_spec",
        "description": "Wireframe specification: screen inventory, component descriptions, user flows, interaction states.",
        "triggers": [
            "wireframe", "mockup", "low-fi", "information architecture", "IA",
            "screen flow", "wireframe spec", "lo-fi", "prototype spec",
            "user flow", "navigation design",
        ],
        "preferred_tools": ["write_file", "read_file", "read_kb", "write_kb"],
        "preferred_agents": ["ux_design_agent"],
        "supported_modes": ["chat", "plan"],
        "tags": ["ux", "design", "wireframes"],
        "body": """\
## Wireframe Specification Protocol

**Step 1 — Information Architecture:**
- Map the full site/app structure as a tree diagram (text format).
- Define primary navigation, secondary navigation, and footer links.
- Identify top-level user tasks and the shortest path to each.

**Step 2 — Screen Inventory:**
List every screen/view with:
- Screen ID (e.g. SCR-001)
- Screen name
- Primary user task served
- Entry points (how users reach this screen)
- Exit points (where users can go from here)

**Step 3 — Component-Level Specification:**
For each screen:
- **Purpose:** one sentence.
- **Layout:** describe the grid/sections (header, sidebar, main content, footer).
- **Components:** list each UI element with:
  - Type (button, input, card, table, modal…)
  - Label/placeholder text
  - Behaviour (what happens on click/hover/input)
  - Validation rules (if applicable)
- **Primary action:** the most important thing users do on this screen.
- **Edge cases:** empty state, loading state, error state, maximum content state.

**Step 4 — Interaction States:**
For each interactive element:
- Default / Hover / Active / Focus / Disabled / Loading / Success / Error

**Step 5 — User Flow Annotations:**
- Happy path: step-by-step numbered flow for the primary task.
- Alternative paths: branch points with conditions.
- Error recovery paths.

**Handoff Checklist:**
- All screens inventoried.
- All states documented.
- Edge cases covered.
- Annotations clear enough for engineering without a meeting.
""",
    },
    {
        "name": "usability_testing",
        "description": "Usability test plan: tasks, success criteria, metrics, script, analysis framework.",
        "triggers": [
            "usability test", "usability study", "user testing", "think aloud",
            "task success rate", "task completion", "moderated testing", "unmoderated testing",
            "usability evaluation",
        ],
        "preferred_tools": ["write_docx", "read_kb", "write_kb", "search_web"],
        "preferred_agents": ["ux_design_agent", "research_agent"],
        "supported_modes": ["research", "chat"],
        "tags": ["ux", "research", "testing"],
        "body": """\
## Usability Testing Protocol

**Step 1 — Test Plan:**
- Research question: "Can users complete [task] without [specific confusion/error]?"
- Method: moderated (remote/in-person) or unmoderated (recorded sessions).
- Participants: 5–8 per user segment (5 uncovers ~85% of major usability issues).
- Recruiting criteria: match target persona — role, usage frequency, technical proficiency.

**Step 2 — Task Design:**
For each task:
- Task scenario (realistic context, not instructions): "You've just received an order for product X. Complete the checkout."
- Success criteria (observable, not subjective): "User completes checkout without requesting help."
- Success metric: completion rate + time on task.
- Failure triggers: gives up, asks for help, navigates away.

**Step 3 — Test Script:**
1. Intro (5 min): purpose, consent, recording notice, no wrong answers.
2. Warm-up (5 min): background questions to understand context.
3. Tasks (20–30 min): present one at a time. "Think aloud — say what you're thinking."
   - Do NOT help — say "What would you do next?" if they get stuck.
   - Note: hesitations, errors, comments, expressions.
4. Post-task questions (after each task): "How difficult was that? (1–7 scale) Why?"
5. Debrief (5 min): overall impressions, anything confusing, anything missing.

**Step 4 — Metrics:**
- Task completion rate (% succeeding without help).
- Time on task.
- Error rate.
- System Usability Scale (SUS) post-session questionnaire.

**Step 5 — Analysis:**
- Rainbow spreadsheet: rows = issues, columns = participants, cells = observed/not.
- Frequency × severity = priority.
- Group issues by: navigation, labelling, visual hierarchy, workflow, content clarity.

**Step 6 — Report:**
- Executive summary: top 3 insights.
- Issue catalogue with severity, frequency, evidence quote, recommendation.
- Positive findings (what worked well).
- Use `write_docx` for the final report.
""",
    },
]
