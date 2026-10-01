# Visual review checklist

Review the running page, not only source code.

## Required viewports

- Desktop: approximately 1440 × 900.
- Tablet: approximately 1024 × 768.
- Phone: approximately 390 × 844.

## Hierarchy

- Can a new user identify current assets, drawdown, remaining risk budget, and next action in five seconds?
- Is there one clear primary action per region?
- Are assumptions and manually entered data visually distinguished from observed results?

## Layout and content

- No clipped text, unintended horizontal scroll, overlapping fixed navigation, or inaccessible controls.
- Chinese typography wraps naturally; currency and percentages do not split awkwardly.
- Empty states explain the next useful action without promotional copy.
- Tables either adapt, scroll intentionally, or become cards on narrow screens.

## Interaction

- Exercise every tab and the main create/edit path.
- Verify range inputs and numeric inputs update dependent results immediately.
- Refresh once to confirm persistent data survives.
- Check focus visibility and labels for inputs and buttons.

## Build proof

- Run the TypeScript check and production build.
- Inspect browser console errors.
- Stop when the acceptance criteria pass; record remaining omissions rather than adding unrelated polish.
