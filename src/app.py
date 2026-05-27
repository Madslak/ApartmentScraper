import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
from database import init_db, get_config, save_config, get_all_listings

st.set_page_config(page_title="Apartment Scout", page_icon="🏠", layout="wide")

init_db()

NEIGHBORHOODS = ["Nørrebro", "Frederiksberg", "Indre By", "Vesterbro", "Østerbro", "Amager", "Valby", "Other"]

page = st.sidebar.radio("Navigation", ["🔍 Results", "⚙️ Config"])

# ── Config page ──────────────────────────────────────────────────────────────
if page == "⚙️ Config":
    st.title("⚙️ Search Configuration")
    config = get_config()

    st.subheader("Criteria")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Price (DKK)**")
        price_max = st.number_input("Max price", value=config["price_max"], step=100000, format="%d")
        price_leniency = st.slider("Leniency %", 0, 50, int(config["price_leniency"]), key="price_len")
        price_hard = st.toggle("Hard limit", value=config["price_hard"], key="price_hard")
        if price_leniency > 0:
            ceiling = int(price_max * (1 + price_leniency / 100))
            label = "blocked above" if price_hard else f"soft match up to {ceiling:,} kr".replace(",", ".")
            st.caption(f"Leniency: {label}")

    with col2:
        st.markdown("**Size (m²)**")
        size_min = st.number_input("Min size", value=config["size_min"], step=5, format="%d")
        size_leniency = st.slider("Leniency %", 0, 50, int(config["size_leniency"]), key="size_len")
        size_hard = st.toggle("Hard limit", value=config["size_hard"], key="size_hard")
        if size_leniency > 0:
            floor = int(size_min * (1 - size_leniency / 100))
            label = "blocked below" if size_hard else f"soft match down to {floor} m²"
            st.caption(f"Leniency: {label}")

    with col3:
        st.markdown("**Rooms**")
        rooms_min = st.number_input("Min rooms", value=config["rooms_min"], step=1, min_value=1, format="%d")
        rooms_hard = st.toggle("Hard limit", value=config["rooms_hard"], key="rooms_hard")

    st.divider()
    st.subheader("Neighborhood Multipliers")
    st.caption("Higher multiplier = stronger preference. Nørrebro = 1.0 is the baseline.")

    multipliers = config.get("neighborhood_multipliers", {})
    nb_cols = st.columns(len(NEIGHBORHOODS))
    new_multipliers = {}
    for i, nb in enumerate(NEIGHBORHOODS):
        with nb_cols[i]:
            val = multipliers.get(nb, 0.55)
            new_multipliers[nb] = st.slider(nb, 0.0, 1.0, float(val), step=0.01, key=f"nb_{nb}")

    st.divider()
    if st.button("💾 Save configuration", type="primary"):
        new_config = {
            "price_max": int(price_max),
            "price_leniency": price_leniency,
            "price_hard": price_hard,
            "size_min": int(size_min),
            "size_leniency": size_leniency,
            "size_hard": size_hard,
            "rooms_min": int(rooms_min),
            "rooms_hard": rooms_hard,
            "neighborhood_multipliers": new_multipliers,
        }
        save_config(new_config)
        st.success("Configuration saved!")

    st.divider()
    st.subheader("Manual pipeline run")
    st.caption("Trigger a scrape right now instead of waiting for the scheduled run.")
    if st.button("▶️ Run pipeline now"):
        with st.spinner("Scraping Boligsiden.dk..."):
            import subprocess, sys
            result = subprocess.run(
                [sys.executable, "pipeline.py"],
                capture_output=True, text=True,
                cwd=str(__import__("pathlib").Path(__file__).parent)
            )
        if result.returncode == 0:
            st.success("Pipeline complete! Switch to Results to see listings.")
            st.code(result.stdout)
        else:
            st.error("Pipeline failed.")
            st.code(result.stderr)

# ── Results page ─────────────────────────────────────────────────────────────
else:
    st.title("🔍 Apartment Results")

    listings = get_all_listings()

    if not listings:
        st.info("No listings yet. Go to ⚙️ Config and click **Run pipeline now** to scrape.")
        st.stop()

    df = pd.DataFrame(listings)

    # Sidebar filters
    st.sidebar.divider()
    st.sidebar.subheader("Quick filters")
    show_soft = st.sidebar.toggle("Show soft-limit matches", value=True)
    nb_filter = st.sidebar.multiselect("Neighborhood", NEIGHBORHOODS, default=NEIGHBORHOODS)

    if not show_soft:
        df = df[df["is_soft_match"] == 0]
    if nb_filter:
        df = df[df["neighborhood"].isin(nb_filter)]

    st.metric("Listings shown", len(df))

    def row_color(row):
        if row["is_soft_match"]:
            return ["background-color: #fff3cd"] * len(row)
        return [""] * len(row)

    display_cols = ["title", "price", "size", "rooms", "neighborhood", "score", "address", "first_seen"]
    df_display = df[display_cols].copy()
    df_display["price"] = df_display["price"].apply(lambda x: f"{int(x):,}".replace(",", ".") + " kr")
    df_display["score"] = df_display["score"].apply(lambda x: f"{x:.2f}")
    df_display["first_seen"] = pd.to_datetime(df_display["first_seen"]).dt.strftime("%d/%m %H:%M")

    styled = df_display.style.apply(
        lambda row: row_color(df.loc[row.name]),
        axis=1,
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Listing details")
    selected_title = st.selectbox("Select a listing", df["title"].tolist())
    if selected_title:
        row = df[df["title"] == selected_title].iloc[0]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Price", f"{int(row['price']):,} kr".replace(",", "."))
            st.metric("Size", f"{row['size']} m²")
            st.metric("Rooms", row["rooms"])
        with col2:
            st.metric("Score", f"{row['score']:.2f}")
            st.metric("Neighborhood", row["neighborhood"])
            soft_label = "⚠️ Soft match (outside strict limits)" if row["is_soft_match"] else "✅ Within limits"
            st.info(soft_label)
        st.markdown(f"**Address:** {row['address']}")
        st.markdown(f"**First seen:** {row['first_seen']}")
        st.link_button("Open on Boligsiden.dk", row["url"])
