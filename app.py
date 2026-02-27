import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION IA (AUTO-DÉTECTION)
model = None
selected_model_name = "Recherche..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if available_models:
            best_model = next((m for m in available_models if "2.5" in m or "2.0" in m or "1.5" in m), available_models[0])
            model = genai.GenerativeModel(best_model)
            selected_model_name = best_model
    except Exception as e:
        st.error(f"Erreur API : {e}")

# 3. CHARGEMENT DES DONNÉES (AVEC VIDAGE DE CACHE)
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    df = conn.read(worksheet="Prospection")
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()
nom_col = "Nom de l'entité"

# 4. GESTION DU DÉBIT (6 RPM)
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=11)

# --- INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Christophe")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Cache : Actif")

# Barre de recherche
search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# TABLEAU DE BORD (Priorité réintégrée)
cols_tableau = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
cols_existantes = [c for c in cols_tableau if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Sélectionner une cible :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MISE À JOUR MANUELLE ---
    st.subheader("📝 Suivi Commercial")
    c1, c2 = st.columns(2)
    with c1:
        # Statut
        opt_s = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        v_s = str(row.get("Statut Follow-up", "")).strip()
        n_statut = st.selectbox("Statut :", opt_s, index=opt_s.index(v_s) if v_s in opt_s else 0)
        
        # Priorité (Correction de la disparition)
        opt_p = ["P1", "P2", "P3"]
        v_p = str(row.get("Priorité", "")).strip().upper()
        n_prio = st.selectbox("Priorité :", opt_p, index=opt_p.index(v_p) if v_p in opt_p else 2)
        
    with c2:
        n_com = st.text_area("Notes / Commentaires :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Sauvegarder les modifications"):
        df.at[idx, "Statut Follow-up"] = n_statut
        df.at[idx, "Priorité"] = n_prio
        df.at[idx, "Commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear() # Force la relecture immédiate
        st.success("✅ Données enregistrées !")
        st.rerun()

    # --- SECTION 2 : ANALYSE IA (6 RPM) ---
    st.divider()
    st.subheader("🤖 Analyse Stratégique")
    attente = max(0, 11.0 - (datetime.now() - st.session_state.last_request_time).total_seconds())

    if st.button(f"🚀 Enrichir {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Quota 6 RPM : Attendez {int(attente)}s.")
        else:
            with st.status("Recherche de signaux faibles...") as status:
                st.session_state.last_request_time = datetime.now()
                prompt = f"Expert CIB. Analyse {selected_company}. JSON: {{'esg': '...', 'actu': '...', 'angle': '...', 'score': 1-5}}"
                try:
                    response = model.generate_content(prompt)
                    res = json.loads(response.text[response.text.find('{'):response.text.rfind('}')+1])
                    
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    df.at[idx, "Potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Analyse terminée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")

    # --- SECTION 3 : FICHE QUALITATIVE (FINANCES RÉELLES) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Indicateurs Financiers")
        st.write(f"**CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Nette :** {row.get('Dette Nette (M€)', 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get('Trésorerie (M€)', 'N/A')} M€")
        st.write(f"**Levier :** {row.get('Levier (x)', 'N/A')} x")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'Non analysé')}")
        st.error(f"**Controverses :** {row.get('Controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche")
        st.success(f"**Angle :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"**Dernière News :** {row.get('Actualité Récente', 'N/A')}")
        st.write(f"**Score Potentiel :** ⭐ {row.get('Potentiel (1-5)', '0')}/5")
        st.write(f"**Maison Mère :** {row.get('Maison Mère (Groupe)', 'N/A')}")