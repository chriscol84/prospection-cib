import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="CRM CIB Christophe", layout="wide", page_icon="💼")

# --- 2. IA & DEEP SEARCH (GROUNDING) ---
model = None
selected_model_name = "Scan du compte..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if models:
            best_m = next((m for m in models if "2.0" in m or "1.5" in m), models[0])
            # ACTIVATION DE LA RECHERCHE GOOGLE
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best_m
    except Exception as e:
        st.error(f"Erreur API : {e}")

# --- 3. CHARGEMENT & DÉTECTION INTELLIGENTE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=10)
def load_data():
    data = conn.read(worksheet="Prospection")
    # Nettoyage radical des colonnes (minuscules, sans espaces, sans parenthèses)
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

# FONCTION POUR TROUVER UNE COLONNE SANS SE TROMPER
def find_col(keywords, default):
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return default

# Mapping automatique (Cherche le mot clé dans tes 18 colonnes)
COL_NOM = find_col(["Dénomination", "Nom (FR)", "Sociale"], "Nom (FR) (Dénomination sociale)")
COL_CA = find_col(["Chiffre d'affaires", "CA (M€)"], "CA (M€) (Chiffre d'affaires)")
COL_EBITDA = find_col(["EBITDA", "Rentabilité"], "EBITDA (M€) (Rentabilité opérationnelle)")
COL_DETTE = find_col(["Dette Financière", "Endettement"], "Dette Financière Brute (Endettement total)")
COL_CASH = find_col(["Trésorerie", "Liquidités"], "Trésorerie (M€) (Liquidités)")
COL_PRIO = find_col(["Priorité", "P1-P3"], "Priorité (P1-P3)")
COL_ACTU = find_col(["Actualité", "News"], "Dernière Actualité (Signal faible / M&A / News)")
COL_ESG = find_col(["Controverses", "ESG"], "Controverses (ESG) (Risques identifiés)")
COL_ANGLE = find_col(["Angle d'Attaque", "Finance"], "Angle d'Attaque (Trade Finance, Refi, Acquisition Finance)")
COL_ACCROCHE = find_col(["Accroche", "Ice breaker"], "Accroche Personnalisée (Ice breaker ciblé)")

# --- 4. GESTION DU DÉBIT (6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE ---
st.title("💼 CRM Prospection CIB - Christophe")
st.caption(f"🤖 IA : `{selected_model_name}` | Mode : Deep Search Actif")

with st.sidebar:
    st.header("Paramètres")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser la base"):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.write("**Colonnes détectées :**")
    st.write(df.columns.tolist())

# Filtrage
mask = df[COL_NOM].str.contains(search_query, case=False, na=False)
filtered_df = df[mask]

st.subheader("📋 Liste des cibles")
st.dataframe(filtered_df[[COL_NOM, COL_PRIO, COL_CA]], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_target = st.selectbox("🎯 Sélectionner pour analyse :", filtered_df[COL_NOM].tolist())
    idx = df[df[COL_NOM] == selected_target].index[0]
    row = df.loc[idx]

    # --- 6. ÉDITION MANUELLE ---
    st.subheader(f"📝 Gestion : {selected_target}")
    c1, c2 = st.columns(2)
    with c1:
        p_list = ["P1", "P2", "P3"]
        v_p = str(row.get(COL_PRIO, "P3")).strip()[:2].upper() # Extrait 'P1'
        n_prio = st.selectbox("Priorité :", p_list, index=p_list.index(v_p) if v_p in p_list else 2)
    with c2:
        n_note = st.text_area("Notes / Accroche :", value=str(row.get(COL_ACCROCHE, "")))

    if st.button("💾 Enregistrer"):
        df.at[idx, COL_PRIO] = n_prio
        df.at[idx, COL_ACCROCHE] = n_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Enregistré !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (CA, EBITDA, DETTE, CASH) ---
    st.divider()
    st.subheader("🤖 Deep Search : Extraction financière web")
    
    attente = max(0, 11.5 - (datetime.now() - st.session_state.last_request_time).total_seconds())

    if st.button(f"🚀 Lancer la recherche financière pour {selected_target}"):
        if attente > 0:
            st.warning(f"⏳ Attendez {int(attente)}s.")
        else:
            with st.status("Recherche web en cours...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                prompt = f"Expert CIB. Analyse {selected_target}. Trouve CA, EBITDA, Dette brute et Cash 2024. Réponds en JSON : {{'ca':0, 'ebitda':0, 'dette':0, 'cash':0, 'esg':'', 'actu':'', 'angle':''}}"
                try:
                    response = model.generate_content(prompt)
                    res = json.loads(response.text[response.text.find('{'):response.text.rfind('}')+1])
                    
                    # Mise à jour
                    df.at[idx, COL_CA] = res.get('ca', row.get(COL_CA))
                    df.at[idx, COL_EBITDA] = res.get('ebitda', row.get(COL_EBITDA))
                    df.at[idx, COL_DETTE] = res.get('dette', row.get(COL_DETTE))
                    df.at[idx, COL_CASH] = res.get('cash', row.get(COL_CASH))
                    df.at[idx, COL_ESG] = res.get('esg', '')
                    df.at[idx, COL_ACTU] = res.get('actu', '')
                    df.at[idx, COL_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données trouvées !", state="complete")
                    st.rerun()
                except Exception as e: st.error(f"Erreur : {e}")

    # --- 8. FICHE FINALE ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_target}")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("### 💰 Finances")
        st.metric("CA", f"{row.get(COL_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(COL_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(COL_DETTE, '0')} M€")
        st.write(f"**Trésorerie :** {row.get(COL_CASH, '0')} M€")
    with f2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**ESG :** {row.get(COL_ESG, 'N/A')}")
    with f3:
        st.markdown("### 🎯 Approche")
        st.success(f"**Angle :** {row.get(COL_ANGLE, 'N/A')}")