# Value Sniper — Strategy Philosophy

## The Problem With Buying Stocks

Most retail investors buy stocks one of two ways: on emotion ("this company is great, I'm in") or on a price target from an article they read. Neither approach tells you *when* to buy, *why* that price is defensible, or *what* would need to happen for the trade to fail.

The result is a specific kind of anxiety that has nothing to do with whether the company is good. You bought at $450. It drops to $410. You don't know if $410 is a buying opportunity or the start of something worse. You hold. It drops to $380. Now you're paralysed. You don't sell because you didn't plan for this. You don't buy more because you have no thesis for why $380 is better than $350.

That paralysis — not the loss itself — is what causes most retail investors to exit at the worst possible time.

Value Sniper is built to solve that specific problem.

---

## What the System Actually Does

Value Sniper does not predict where a stock will go. It identifies where a stock has *structural* reasons to stop falling — price levels where multiple independent forces converge to create buying pressure.

When the system outputs Level 1 at $407, that number is not a guess. It is the centroid of a K-Means cluster built from:

- The strike price causing maximum pain to options market makers
- Unfilled institutional breakaway gaps from prior sessions
- The 200-day moving average (the line institutions watch)
- The lower Bollinger Band (statistical oversold boundary)
- The 10-year Treasury yield position (macro stress signal)
- The VIX regime (fear level adjustment)
- Sector strength relative to the broader market
- Market breadth (is this a healthy dip or a broad breakdown?)
- RSI and ADX trend confirmation

Nine independent protocols. One number. If they disagree, the clustering reflects that uncertainty. If they agree tightly, the level is high-conviction.

This is not technical analysis in the traditional sense. There are no chart patterns, no subjective trend lines, no "it looks like a head and shoulders." Every input is derived from market microstructure data — the mechanics of how options markets and institutional positioning actually influence price.

---

## The Three Levels

The system outputs three levels for each analysis, not one. This is deliberate.

**Level 1 — Dip Entry**
The most likely support. The level that gets hit during normal pullbacks in healthy markets. If you're already bullish on a name and just want a better entry than market price, this is where you scale in initially. Roughly 50–60% of analyses produce a touch at this level within 90 days.

**Level 2 — Deep Value**
A genuine correction level. The kind of support you expect during sector rotation, mild macro shock, or earnings disappointment. Historical hit rate is lower (~25%) but when it hits, the thesis is usually very clean.

**Level 3 — Bear Market Entry**
The capitulation floor. This is where the stock would trade in a genuine bear event — a rate shock, a sector unwind, a black swan. Hit rate is low by design (<5–10%). This is your "I want to buy as much as I can if this ever trades here" level. When it hits, you're buying at the price that held during maximum fear.

The position sizing guidance (20%/30%/50% of intended allocation) reflects this. You don't deploy full capital at Level 1 because Level 2 might fill. You deploy progressively, so your average cost improves with every level hit.

---

## When the System Says No

One of the most important outputs is not a level — it is silence.

The Defensive Shift mechanism triggers when:
- Tech sector is underperforming the broader market
- Market breadth shows a narrow rally (few stocks leading)
- Breadth divergence between SPY and equal-weight RSP exceeds 5%

When this fires, Level 1 is deleted. The system moves all levels lower and widens the safety margins. It is saying: "the market structure is broken right now, the normal dip-buy logic does not apply."

In the 2022 bear market, the system correctly refused to generate aggressive entries for MSFT, AAPL, and META for most of the year. It detected the sector breakdown and stayed defensive. This is not a failure mode — it is the system working exactly as designed.

Staying in cash during a confirmed downtrend is a return. It just does not appear in a P&L statement.

---

## The Right Way to Use This Tool

Value Sniper is not a standalone portfolio strategy. It is a precision entry layer designed to sit on top of a broader investment approach.

**The intended setup:**

```
Layer 1 — ETF Base (always running)
  Monthly DCA into SPY, QQQ, or a total market index.
  No decisions required. Set and forget.

Layer 2 — Sniper Entries (opportunistic)
  When a high-conviction tech holding hits a Sniper level,
  size in with concentrated capital.
  You have a documented thesis. You know the floor.
  You know what would invalidate the trade.
```

The ETF layer protects you during periods when the Sniper finds no entries (markets only go up, no pullbacks offered). Your capital keeps compounding through the index. The Sniper layer gives you below-market cost basis on individual names when the market offers it.

In the 2022 bear market, the SPY DCA baseline lost only -6.4% while individual tech stocks lost 30–65%. The Sniper was mostly in cash on single names. The ETF layer kept working. This is the correct behaviour.

In recovery from the 2022 bottom (July 2022 → January 2024), the Sniper generated entries with 100% win rate on closed trades. The entries were made at levels that were genuinely defended — not catches of falling knives, but purchases near real structural floors.

---

## What This Tool Cannot Do

It is worth being honest about the limits.

**It cannot predict direction.** A Level 2 entry that was correct about support can still see the stock fall to Level 3 before recovering. The levels are support zones, not guarantees.

**It cannot account for fundamental implosion.** If a company reports a fraud, a catastrophic earnings miss, or regulatory shutdown, no technical support level holds. The system assumes the company remains a viable going concern.

**It is calibrated for Nasdaq-100 tech equities.** The protocols (options max pain weighting, sector strength via XLK, macro sensitivity to yields) are designed for large-cap US tech. Results on smaller caps, commodities, or non-US markets have not been validated.

**Historical options data is unavailable.** Backtests run in historical mode skip Protocol C (options max pain) because yfinance only provides live options chains. This means backtested levels are slightly less accurate than live analyses, which have the full 9-protocol signal.

**It does not tell you when to sell.** The profit target framework in the benchmark is one interpretation. Some users hold indefinitely. Some use the next Sniper analysis as a re-entry guide after an exit. The tool gives you the entry thesis; the exit is your decision.

---

## The Honest Summary

This tool will not make you rich faster than holding an index fund. In a strong bull market, any strategy that stays invested wins, and the Sniper's discipline of waiting for levels means it misses some of that run.

What it does instead is remove a specific type of loss: the loss that comes from entering at the wrong price with no thesis and no plan. Every entry made through the system has a documented reason. The nine protocols are visible. The risk score is visible. The defensive shift is visible. You know, before you click buy, exactly what the market is telling you about that price.

That changes how you hold. You are not wondering if you made a mistake. You are watching whether a specific, documented thesis holds or breaks. If it breaks, you know. If it holds, you know. The uncertainty that causes panic-selling evaporates, because the uncertainty was never about the price — it was about not having a reason to be in the trade in the first place.

That is what the system is for.
