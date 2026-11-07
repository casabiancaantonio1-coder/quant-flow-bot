import os
import sys
import math
import requests
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

# YOUR EXACT DISCORD WEBHOOK URLS ARE PLUGGED IN HERE:
FREE_WEBHOOK_URL = os.getenv("FREE_WEBHOOK_URL", "PASTE_FREE_WEBHOOK_HERE")
VIP_WEBHOOK_URL = os.getenv("VIP_WEBHOOK_URL", "PASTE_VIP_WEBHOOK_HERE")
SIGNUP_LINK = "https://whop.com/your-link-here"

TICKERS = ['SPY', 'QQQ', 'NVDA', 'TSLA', 'AAPL', 'AMD', 'META', 'MSFT', 'AMZN', 'PLTR', 'COIN', 'SMCI']

def scan_quant_flow():
    plays = []
    market_levels = []
    print("Scanning options chains for Expected Moves, Gamma Walls & Whale Sweeps...")

    for symbol in TICKERS:
        try:
            tk = yf.Ticker(symbol)
            spot = float(tk.fast_info['last_price'])
            expirations = tk.options[:2]

            for idx, exp in enumerate(expirations):
                chain = tk.option_chain(exp)
                calls, puts = chain.calls.copy(), chain.puts.copy()
                if calls.empty or puts.empty:
                    continue

                atm_c = (calls['strike'] - spot).abs().idxmin()
                atm_p = (puts['strike'] - spot).abs().idxmin()
                straddle = float(calls.loc[atm_c, 'lastPrice']) + float(puts.loc[atm_p, 'lastPrice'])
                exp_move = round(straddle * 0.85, 2)
                low_band, high_band = round(spot - exp_move, 2), round(spot + exp_move, 2)

                call_wall = calls.loc[calls['openInterest'].idxmax(), 'strike'] if calls['openInterest'].max() > 0 else spot
                put_wall = puts.loc[puts['openInterest'].idxmax(), 'strike'] if puts['openInterest'].max() > 0 else spot

                if idx == 0 and symbol in ['SPY', 'QQQ', 'NVDA', 'TSLA']:
                    market_levels.append(
                        f"${symbol} ({exp[5:]}): ±${exp_move:.2f} [${low_band:.0f}–${high_band:.0f}] | Put Wall: ${put_wall:g} | Call Wall: ${call_wall:g}"
                    )

                for opt_type, df in [('CALL', calls), ('PUT', puts)]:
                    cond = (df['volume'] >= 1000) & (df['openInterest'] >= 100) & ((df['volume'] / df['openInterest']) >= 2.2)
                    for _, row in df[cond].iterrows():
                        vol, oi = int(row['volume']), int(row['openInterest'])
                        last_p, strike = float(row['lastPrice']), float(row['strike'])
                        iv = float(row['impliedVolatility']) * 100
                        ratio = round(vol / oi, 1)
                        spend = int(vol * last_p * 100)
                        otm_pct = ((strike - spot) / spot * 100) if opt_type == 'CALL' else ((spot - strike) / spot * 100)

                        if spend >= 100000:
                            score = int(min(99, min(45, math.log10(max(spend, 1)) * 7.5) + min(35, ratio * 4.5) + (19 if otm_pct > 0.5 else 8)))
                            plays.append({
                                'Ticker': f"${symbol}",
                                'Spot': f"${spot:.2f}",
                                'Exp': exp[5:],
                                'Contract': f"${strike:g} {opt_type}",
                                'Last': f"${last_p:.2f}",
                                'OTM%': f"{otm_pct:+.1f}%",
                                'Vol/OI': f"{ratio}x",
                                'IV': f"{iv:.0f}%",
                                'Exp Range': f"±${exp_move:.2f}",
                                'Walls (P/C)': f"${put_wall:g}/${call_wall:g}",
                                'Flow ($)': f"${spend:,.0f}",
                                'Score': f"{score}/99",
                                'Raw_Rank': score * spend
                            })
        except Exception:
            continue

    df_out = pd.DataFrame(plays)
    if not df_out.empty:
        df_out = df_out.sort_values(by='Raw_Rank', ascending=False).head(10)
    return df_out, market_levels

def build_chart(df, market_levels, filename="quant_flow.png"):
    cols = ['Ticker', 'Spot', 'Exp', 'Contract', 'Last', 'OTM%', 'Vol/OI', 'IV', 'Exp Range', 'Walls (P/C)', 'Flow ($)', 'Score']
    plot_df = df[cols]

    fig, ax = plt.subplots(figsize=(15, 6.2), dpi=220)
    fig.patch.set_facecolor('#090d16')
    ax.set_facecolor('#090d16')
    ax.axis('off')

    now_str = datetime.now().strftime("%b %d, %Y | %I:%M %p EST")
    plt.suptitle(f"INSTITUTIONAL OPTIONS FLOW & DEALER GAMMA ENGINE  ({now_str})", color='#ffffff', fontsize=14, fontweight='bold', y=0.96)
    plt.title("0DTE / WEEKLY IMPLIED RANGES:  " + "   •   ".join(market_levels[:3]), color='#38bdf8', fontsize=9, fontweight='bold', pad=12)

    widths = [0.06, 0.07, 0.06, 0.11, 0.06, 0.06, 0.06, 0.05, 0.08, 0.11, 0.10, 0.07]
    table = ax.table(cellText=plot_df.values, colLabels=plot_df.columns, colWidths=widths, loc='center', cellLoc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.85)

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor('#1e293b')
        if r == 0:
            cell.set_facecolor('#0f172a')
            cell.set_text_props(color='#38bdf8', fontweight='bold')
        else:
            cell.set_facecolor('#090d16' if r % 2 == 1 else '#0f1523')
            val = str(plot_df.iloc[r-1, c])
            if c == 3 and 'CALL' in val:
                cell.set_text_props(color='#22c55e', fontweight='bold')
            elif c == 3 and 'PUT' in val:
                cell.set_text_props(color='#ef4444', fontweight='bold')
            elif c == 10:
                cell.set_text_props(color='#f59e0b', fontweight='bold')
            elif c == 11:
                cell.set_text_props(color='#a855f7', fontweight='bold')
            else:
                cell.set_text_props(color='#e2e8f0')

    plt.figtext(0.5, 0.025, "Walls (P/C) = Highest Put Support / Call Resistance  •  Exp Range = ±1 SD Implied Move  •  Score = Flow Velocity + OTM Aggression", ha="center", fontsize=8.5, color="#94a3b8")
    plt.tight_layout()
    plt.savefig(filename, facecolor=fig.get_facecolor(), bbox_inches='tight', pad_inches=0.3)
    plt.close()

def dispatch_alerts(df, levels, mode="vip", image_path="quant_flow.png"):
    top = df.iloc[0]
    second = df.iloc[1] if len(df) > 1 else top
    tags = " ".join(df['Ticker'].unique()[:6])
    spy_lvl = levels[0] if levels else ""
    all_levels_text = "\n".join([f"• `{lvl}`" for lvl in levels])

    lottos = df[df['Last'].str.replace('$', '', regex=False).astype(float) <= 2.50]
    lotto_line = ""
    if not lottos.empty:
        lt = lottos.iloc[0]
        lotto_line = (
            f"\n🎰 **VIP WHALE LOTTO ALERT (Under $2.50):** `{lt['Ticker']}` **{lt['Contract']}** "
            f"(Exp `{lt['Exp']}` @ `{lt['Last']}`) — **{lt['Flow ($)']}** inflow at `{lt['Vol/OI']}` Vol/OI (`{lt['Score']}`)"
        )

    vip_msg = (
        f"⚡ **LIVE VIP INSTITUTIONAL SWEEP & GAMMA FEED** ⚡\n\n"
        f"🏆 **#1 Conviction Sweep ({top['Score']}):** `{top['Ticker']}` **{top['Contract']}** (Exp `{top['Exp']}` @ `{top['Last']}`) — "
        f"**{top['Flow ($)']}** swept (`{top['Vol/OI']}` Vol/OI | `{top['OTM%']}` OTM | Walls: `{top['Walls (P/C)']}`)\n"
        f"🥈 **#2 Sweep ({second['Score']}):** `{second['Ticker']}` **{second['Contract']}** (@ `{second['Last']}`) — **{second['Flow ($)']}** (`{second['Vol/OI']}` Vol/OI)"
        f"{lotto_line}\n\n"
        f"📐 **VIP Live Dealer Gamma & Expected Move Map:**\n{all_levels_text}"
    )
    if "http" in VIP_WEBHOOK_URL:
        with open(image_path, "rb") as f:
            requests.post(VIP_WEBHOOK_URL, data={"content": vip_msg}, files={"file": f})

    if mode == "free":
        free_msg = (
            f"📊 **DAILY QUANT FLOW & GAMMA RECAP** 📊\n"
            f"🔥 **Top Conviction Sweep ({top['Score']}):** `{top['Ticker']}` **{top['Contract']}** — **{top['Flow ($)']}** traded at **{top['Vol/OI']}** Vol/OI.\n"
            f"🎯 **SPY Dealer Range:** `{spy_lvl}`\n"
            f"🔓 *VIP Members get live alerts every 30 mins + Under-$2.50 Whale Lotto Sweeps. Try VIP Free for 3 Days:* {SIGNUP_LINK}\n\n"
            f"📲 **Copy-Paste Social Post (Stocktwits / X / Reddit):**\n"
            f"```{tags} Institutional Whale Flow + Dealer Gamma Walls:\n"
            f"• #1 Conviction Sweep ({top['Score']}): {top['Ticker']} {top['Contract']} ({top['Flow ($)']} inflow at {top['Vol/OI']} Vol/OI)\n"
            f"• {spy_lvl}\n"
            f"Full 10-contract Quant Sheet below 👇```"
        )
        if "http" in FREE_WEBHOOK_URL:
            with open(image_path, "rb") as f:
                requests.post(FREE_WEBHOOK_URL, data={"content": free_msg}, files={"file": f})
    else:
        fomo_teaser = (
            f"🔒 **LIVE INTRADAY WHALE SWEEP JUST HIT `#vip-live-sweeps`** 🔒\n"
            f"• **Conviction Score:** `{top['Score']}`\n"
            f"• **Ticker & Strike:** `[🔒 UNLOCKED IN VIP]` (`{top['OTM%']}` OTM | Exp `{top['Exp']}`)\n"
            f"• **Institutional Inflow:** **{top['Flow ($)']}** swept at **{top['Vol/OI']}** Volume/OI\n"
            f"👉 *Unlock live intraday alerts (3-Day Free Trial):* {SIGNUP_LINK}"
        )
        if "http" in FREE_WEBHOOK_URL:
            requests.post(FREE_WEBHOOK_URL, data={"content": fomo_teaser})

if __name__ == "__main__":
    run_mode = sys.argv[1] if len(sys.argv) > 1 else "free"
    df_flow, lvls = scan_quant_flow()
    if not df_flow.empty:
        build_chart(df_flow, lvls)
        dispatch_alerts(df_flow, lvls, mode=run_mode)
        print(f"Success! Dispatched {run_mode.upper()} Quant Alerts to Discord.")