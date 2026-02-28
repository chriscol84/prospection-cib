import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
import re
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# --- 2. IA : FORCAGE SUR 1.5 FLASH (POUR MAXIMISER LE QUOTA) ---
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On utilise le 1.5 Flash qui est beaucoup moins restrictif que le 2.0
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            tools=[{"google_search_retrieval": {}}]
        )
    except Exception as e:
        st.error(f"Erreur d'initialisation de l'API : {e}")

# --- 3. CHARGEMENT & MAPPING DYNAMIQUE ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    data = conn.read(worksheet="Prospection")
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

def find_column(keywords):
    """Trouve la colonne même si le nom change ou contient des espaces spéciaux."""
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return None

# MAPPING DYNAMIQUE (LE BULLDOZER)
C_NOM    = find_column(["Nom (FR)", "Dénomination", "Nom"])
C_CA     = find_column(["CA (M€)", "Chiffre d'affaires", "CA"])
C_EBITDA = find_column(["EBITDA", "Rentabilité", "Ebitda"])
C_DETTE  = find_column(["Dette Financière", "Endettement", "Dette Brute"])
C_CASH   = find_column(["Trésorerie", "Liquidités", "Cash"])
C_PRIO   = find_column(["Priorité", "P1-P3"])
C_ACTU   = find_column(["Actualité", "Signal faible", "News"])
C_ESG    = find_column(["Controverses", "ESG", "Risques"])
C_ANGLE  = find_column(["Angle", "Attaque", "Approche"])
C_SECT   = find_column(["Secteur", "Industrie"])
C_ACC    = find_column(["Accroche", "Ice breaker"])

if not C_NOM:
    st.error("❌ Erreur : Impossible de trouver la colonne 'Nom' dans votre fichier.")
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_req" not in st.session_state:
    st.session_state.last_req = datetime.now() - timedelta(seconds=15)

# --- 5. INTERFACE UTILISATEUR ---
st.title("🚀 CRM CIB Intelligence - Christophe")
st.info("💡 Modèle 1.5 Flash actif (Grounding Search OK)")

with st.sidebar:
    st.header("Navigation")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser les données"):
        st.cache_data.clear()
        st.rerun()

# Filtrage du DataFrame
mask = df[C_NOM].astype(str).str.contains(search_query, case=False, na=False)
f_df = df[mask]

# Pipeline Principal
st.subheader("📋 Pipeline de Prospection")
st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    
    selected_target = st.selectbox("🎯 Sélectionner une cible :", f_df[C_NOM].tolist())
    
    try:
        idx = df[df[C_NOM] == selected_target].index[0]
        row = df.loc[idx]
    except Exception:
        st.stop()

    # --- 6. ÉDITION MANUELLE ---
    st.subheader(f"📝 Gestion de : {selected_target}")
    col1, col2 = st.columns(2)
    
    with col1:
        p_opts = ["P1", "P2", "P3"]
        val_prio = str(row.get(C_PRIO, "P3"))[:2].upper().strip()
        idx_prio = p_opts.index(val_prio) if val_prio in p_opts else 2
        new_prio = st.selectbox("Définir la priorité :", p_opts, index=idx_prio)

    with col2:
        new_note = st.text_area("Accroche / Notes :", value=str(row.get(C_ACC, "")))

    if st.button("💾 Sauvegarder"):
        df.at[idx, C_PRIO] = new_prio
        df.at[idx, C_ACC] = new_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données sauvegardées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (EXTRACTION WEB FINANCIÈRE) ---
    st.divider()
    st.subheader("🤖 Deep Search : Extraction financière en temps réel")
    
    wait_time = max(0, 15.0 - (datetime.now() - st.session_state.last_req).total_seconds())

    if st.button(f"🚀 Analyser {selected_target}"):
        if wait_time > 0:
            st.warning(f"⏳ Respect du quota : attendez {int(wait_time)}s.")
        elif model is None:
            st.error("IA non configurée.")
        else:
            with st.status("Recherche web (Google Grounding) en cours...", expanded=True) as status:
                st.session_state.last_req = datetime.now()
                
                prompt = f"""
                Recherche les données financières 2024 de {selected_target}. 
                Réponds UNIQUEMENT en JSON (nombres seuls) :
                {{
                    "ca": "valeur CA en M€",
                    "ebitda": "valeur EBITDA en M€",
                    "dette": "Dette brute en M€",
                    "cash": "Trésorerie en M€",
                    "esg": "synthèse risques ESG (10 mots max)",
                    "actu": "dernière news financière",
                    "angle": "angle d'attaque commercial"
                }}
                Si inconnu, mets 0.
                """
                
                try:
                    response = model.generate_content(prompt)
                    raw_txt = response.text
                    res = json.loads(raw_txt[raw_txt.find('{'):raw_txt.rfind('}')+1])
                    
                    # Mise à jour du DataFrame
                    df.at[idx, C_CA] = res.get('ca', row[C_CA])
                    df.at[idx, C_EBITDA] = res.get('ebitda', row[C_EBITDA])
                    df.at[idx, C_DETTE] = res.get('dette', row[C_DETTE])
                    df.at[idx, C_CASH] = res.get('cash', row[C_CASH])
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Analyse terminée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur d'analyse (Quota probable) : {e}")

    # --- 8. FICHE DE SYNTHÈSE QUALITATIVE ---
    st.divider()
    st.subheader(f"🔍 Résultats : {selected_target}")
    f1, f2, f3 = st.columns(3)
    
    with f1:
        st.markdown("### 💰 Finances")
        st.metric("Chiffre d'Affaires", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(C_DETTE, '0')} M€")
        st.write(f"**Trésorerie :** {row.get(C_CASH, '0')} M€")

    with f2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")

    with f3:
        st.markdown("### 🎯 Approche")
        st.success(f"**Angle :** {row.get(C_ANGLE, 'À définir')}")
        st.write(f"**News :** {row.get(C_ACTU, 'N/A')}")