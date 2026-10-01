---
name: finance-dashboard-ui
description: Design, implement, or review polished investment dashboards and financial research interfaces in Quant Copilot. Use for UI architecture, visual styling, financial charts, responsive behavior, interaction states, and visual QA; do not trigger for backend-only financial logic.
---

# Finance Dashboard UI

Build a calm, credible decision interface for long-horizon investors. Optimize for comprehension and risk awareness, not trading excitement.

## A-share product scope

- Treat A-shares as the primary market. Default to Chinese labels, RMB, mainland trading dates, and six-digit codes with exchange suffixes when the data provider requires them.
- Reflect A-share constraints and behavior when relevant: T+1 settlement, price limits, policy sensitivity, liquidity and turnover, sentiment cycles, sector rotation, and delisting/ST risk.
- Do not use AAPL, SPY, USD, US Treasury yields, PDT, or US options rules in the primary workflow unless the user explicitly asks for a cross-market comparison.
- Separate three decisions: market environment sets total equity exposure; sector/mainline evidence sets research priority; company quality, valuation, and invalidation determine the individual position.
- Market strength never overrides the drawdown defense. When signals conflict, risk budget and portfolio survival take priority.

## Product character

- Professional wealth-management workspace: precise, restrained, information-rich without feeling crowded.
- Chinese-first labels and concise copy. Avoid mixed-language navigation unless the user requests it.
- Use color to encode meaning. Profit/loss and risk colors are not decoration.
- Distinguish observed data, user-entered assumptions, and calculated scenarios in the interface.
- Never imply live data, guaranteed returns, or automatic execution when those capabilities do not exist.

Read [references/design-system.md](references/design-system.md) before changing visual language, shared components, dashboards, tables, forms, or charts. Read [references/visual-review.md](references/visual-review.md) before the final browser review.

## Working method

1. Inspect the existing page at its real viewport before editing. Identify the primary decision, supporting evidence, and lower-priority controls.
2. Reuse the existing Next.js, TypeScript, Tailwind, and component seams. Add a dependency only when it materially improves an acceptance criterion.
3. Establish hierarchy before decoration: page shell, primary metric, supporting metrics, actions, details.
4. Make long forms progressive: use a drawer, dialog, expandable panel, or edit mode instead of permanently exposing every field.
5. Include purposeful empty, loading, error, validation, and saved states where the workflow can reach them.
6. Keep interactions keyboard accessible and preserve visible labels. Provide adequate focus states and contrast.
7. Run type checking and production build. Review the page at desktop, tablet, and phone widths using the browser.

## Definition of done

- The most important portfolio state and required next action are understandable within five seconds.
- The interface clearly separates actual portfolio data from estimates and scenarios.
- No horizontal overflow at phone width; dense tables have a deliberate mobile treatment.
- Shared colors, spacing, radii, controls, and financial formats are consistent.
- Interactive controls visibly update calculations and persistent inputs survive refresh.
- Type check and production build pass, followed by a visual review using the repository checklist.
