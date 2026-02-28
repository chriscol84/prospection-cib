import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
import re
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="CRM Prospection Christophe", 
    layout="wide", 
    page_icon="💼"
)

# --- 2. INITIALISATION IA (DÉTECTION AUTOMATIQUE DES MODÈLES DISPONIBLES) ---
model = None
selected_model_name = "Recherche de modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # On liste tous les modèles accessibles pour ta clé
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        
        if available_models:
            # On cherche par priorité : 2.0 Flash, puis 1.5 Flash, puis le premier dispo
            # On retire le préfixe 'models/' si nécessaire pour la configuration
            best_m = next((m for m in available_models if "flash" in m.lower()), available_models[0])
            
            # ACTIVATION DE LA RECHERCHE WEB (GROUNDING)
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best_m
        else:
            st.error("Aucun modèle Gemini trouvé sur ce compte.")
    except Exception as e:
        st.error(f"Erreur d'accès à l'API : {e}")

# --- 3. CHARGEMENT ET DÉTECTION DYNAMIQUE DES COLONNES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    data = conn.read(worksheet="Prospection")
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

def find_column(keywords):
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return None

# Mapping intelligent (Christophe CIB Mapping)
C_NOM    = find_column(["Nom (FR)", "Dénomination", "Nom"])
C_CA     = find_column(["CA (M€)", "Chiffre d'affaires", "CA"])
C_EBITDA = find_column(["EBITDA", "Rentabilité"])
C_DETTE  = find_column(["Dette Financière", "Endettement", "Dette Brute"])
C_CASH   = find_column(["Trésorerie", "Liquidités", "Cash"])
C_PRIO   = find_column(["Priorité", "P1-P3"])
C_ACTU   = find_column(["Actualité", "Signal faible", "News"])
C_ESG    = find_column(["Controverses", "ESG", "Risques"])
C_ANGLE  = find_column(["Angle", "Attaque", "Approche"])
C_SECT   = find_column(["Secteur", "Industrie"])
C_ACC    = find_column(["Accroche", "Ice breaker"])

if not C_NOM:
    st.error("❌ Impossible d'identifier la colonne pivot 'Nom'.")
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_req_time" not in st.session_state:
    st.session_state.last_req_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("🚀 CRM CIB Intelligence - Christophe")
st.info(f"Moteur détecté : **{selected_model_name}** | Statut : Prêt")



with st.sidebar:
    st.header("Filtrage & Actions")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser le Sheet"):
        st.cache_data.clear()
        st.rerun()

# Filtrage
mask = df[C_NOM].astype(str).str.contains(search_query, case=False, na=False)
f_df = df[mask]

st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    target = st.selectbox("🎯 Sélectionner pour analyse :", f_df[C_NOM].tolist())
    idx = df[df[C_NOM] == target].index[0]
    row = df.loc[idx]

    # --- 6. GESTION MANUELLE ---
    st.subheader(f"📝 Suivi : {target}")
    col1, col2 = st.columns(2)
    with col1:
        p_opts = ["P1", "P2", "P3"]
        v_p = str(row.get(C_PRIO, "P3"))[:2].upper()
        n_prio = st.selectbox("Priorité :", p_opts, index=p_opts.index(v_p) if v_p in p_opts else 2)
    with col2:
        n_note = st.text_area("Notes de prospection :", value=str(row.get(C_ACC, "")))

    if st.button("💾 Sauvegarder"):
        df.at[idx, C_PRIO] = n_prio
        df.at[idx, C_ACC] = n_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données sauvegardées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (AVEC GESTION QUOTA) ---
    st.divider()
    st.subheader("🤖 Deep Search : Recherche Financière Web")
    
    wait = max(0, 12.0 - (datetime.now() - st.session_state.last_req_time).total_seconds())

    if st.button(f"🚀 Lancer l'analyse web pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Quota 6 RPM : attendez {int(wait)}s.")
        elif model is None:
            st.error("L'IA n'est pas opérationnelle.")
        else:
            with st.status("Recherche web financière...", expanded=True) as status:
                st.session_state.last_req_time = datetime.now()
                prompt = f"Données financières 2024 de {target}. JSON court: {{'ca':0, 'ebitda':0, 'dette':0, 'cash':0, 'esg':'', 'actu':'', 'angle':''}}"
                try:
                    resp = model.generate_content(prompt)
                    res = json.loads(resp.text[resp.text.find('{'):resp.text.rfind('}')+1])
                    
                    # Mise à jour des colonnes
                    for key, sheet_col in zip(['ca', 'ebitda', 'dette', 'cash'], [C_CA, C_EBITDA, C_DETTE, C_CASH]):
                        df.at[idx, sheet_col] = res.get(key, row[sheet_col])
                    
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données enregistrées !", state="complete")
                    st.rerun()
                except Exception as e:
                    if "429" in str(e):
                        st.error("🛑 Quota quotidien épuisé. Revenez demain !")
                    else:
                        st.error(f"Erreur d'analyse : {e}")

    # --- 8. FICHE FINALE ---
    st.divider()
    st.subheader(f"🔍 Résultats Intelligence Market")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.metric("CA", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(C_DETTE, '0')} M€")
    with f2:
        st.info(f"**Analyse ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")
    with f3:
        st.success(f"**Angle :** {row.get(C_ANGLE, 'À définir')}")
        st.write(f"**Dernière News :** {row.get(C_ACTU, 'N/A')}")