# Quant Copilot visual system

## Visual direction

Aim for an institutional portfolio workspace softened for personal use. Prefer quiet confidence over glossy fintech promotion.

## Tokens

- Canvas: warm neutral `#f4f6f2`; surface: white; subdued surface: `#f7f8f6`.
- Primary ink: deep forest `#10281d`; body ink: slate 700; secondary text: slate 500.
- Brand: emerald 700 for primary actions, emerald 500 for focus, pale emerald for selected states.
- Risk: amber for attention, orange for reduction, red only for danger or destructive actions.
- Positive returns: emerald; negative returns: red. Provide symbols or labels so color is not the sole signal.
- Use one subtle border family and at most three elevation levels.

## Typography and numbers

- Use the system sans stack already in the product. Use weight and size before adding color.
- Page title 28–32px, section title 16–20px, body 14px, metadata 12px.
- Use tabular numerals for currency, percentages, prices, and dates.
- Keep Chinese labels direct. Prefer `当前回撤` over explanatory marketing copy.

## Layout

- Desktop content max width 1440px. Use a 12-column mental grid and 20–24px gaps.
- Tablet collapses secondary columns; phone becomes one column with 16px page padding.
- The first viewport should contain portfolio state, risk state, and one next-action block.
- Do not give every section equal visual weight. One dominant panel per view is enough.

## Components

- Cards: 16–20px radius, 1px neutral border, restrained shadow. Avoid nested shadows.
- Metrics: label, large value, contextual comparison. Do not present a number without its unit or meaning.
- Tabs: compact segmented navigation with a clear selected state; keep descriptions out of narrow navigation.
- Forms: labels remain visible; related controls are grouped. Long create/edit forms are hidden until requested.
- Tables: sticky or clear headers, tabular numbers, comfortable row targets, explicit empty state.
- Charts: label units and time windows. Use tooltips and legends when comparison is not obvious. Never fabricate historical series.
- Motion: 150–220ms for hover, selection, drawer, and calculation feedback. Avoid looping motion.

## Finance-specific invariants

- Mark manual data and scenario outputs as such.
- Show the as-of date for externally sourced data.
- Put risk budget and drawdown before return-chasing signals.
- A target price is an assumption range, not a recommendation badge.
- Destructive portfolio actions require explicit confirmation; editing research notes should auto-save safely.
