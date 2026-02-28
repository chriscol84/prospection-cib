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

# --- 2. INITIALISATION IA (AVEC LE NOUVEAU OUTIL GOOGLE_SEARCH) ---
model = None
selected_model_name = "Recherche de modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # Détection automatique du meilleur modèle disponible
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        
        if available_models:
            # On privilégie le modèle Flash pour la rapidité et le quota
            best_m = next((m for m in available_models if "flash" in m.lower()), available_models[0])
            
            # CORRECTION : Utilisation de 'google_search' au lieu de 'google_search_retrieval'
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search": {}}] 
            )
            selected_model_name = best_m
        else:
            st.error("Aucun modèle Gemini trouvé sur ce compte.")
    except Exception as e:
        st.error(f"Erreur d'accès à l'API : {e}")

# --- 3. CHARGEMENT ET MAPPING DYNAMIQUE DES COLONNES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    data = conn.read(worksheet="Prospection")
    # Nettoyage des noms de colonnes (espaces invisibles)
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

def find_column(keywords):
    """Trouve la colonne par mot-clé pour éviter le KeyError."""
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return None

# MAPPING DYNAMIQUE (Le "Bulldozer" de Christophe)
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
st.info(f"Système opérationnel sur : **{selected_model_name}**")

with st.sidebar:
    st.header("Filtrage & Actions")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser le Sheet"):
        st.cache_data.clear()
        st.rerun()

# Filtrage du DataFrame
mask = df[C_NOM].astype(str).str.contains(search_query, case=False, na=False)
f_df = df[mask]

st.subheader("📋 Pipeline de Prospection")
st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    target = st.selectbox("🎯 Sélectionner pour analyse :", f_df[C_NOM].tolist())
    idx = df[df[C_NOM] == target].index[0]
    row = df.loc[idx]

    # --- 6. GESTION MANUELLE ---
    st.subheader(f"📝 Suivi de {target}")
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
        st.success("Modifications enregistrées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (AVEC GOOGLE_SEARCH) ---
    st.divider()
    st.subheader("🤖 Intelligence Financière Web")
    
    wait = max(0, 12.0 - (datetime.now() - st.session_state.last_req_time).total_seconds())

    if st.button(f"🚀 Lancer la recherche profonde pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Respect du quota : attendez {int(wait)}s.")
        elif model is None:
            st.error("IA non opérationnelle.")
        else:
            with st.status("Interrogation de Google Search...", expanded=True) as status:
                st.session_state.last_req_time = datetime.now()
                # Prompt spécifique pour bpost et autres cibles
                prompt = f"""
                Réalise une recherche financière sur {target}. 
                Réponds EXCLUSIVEMENT en JSON avec des chiffres pour les finances :
                {{
                    "ca": "valeur CA en M€",
                    "ebitda": "valeur EBITDA en M€",
                    "dette": "dette brute en M€",
                    "cash": "trésorerie en M€",
                    "esg": "synthèse risques ESG",
                    "actu": "nouvelle financière majeure",
                    "angle": "conseil approche"
                }}
                Si inconnu, mets 0.
                """
                try:
                    resp = model.generate_content(prompt)
                    # Nettoyage de la réponse pour extraire le JSON
                    raw_txt = resp.text
                    res = json.loads(raw_txt[raw_txt.find('{'):raw_txt.rfind('}')+1])
                    
                    # Remplissage des colonnes
                    for key, col in zip(['ca', 'ebitda', 'dette', 'cash'], [C_CA, C_EBITDA, C_DETTE, C_CASH]):
                        df.at[idx, col] = res.get(key, row[col])
                    
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données enregistrées dans le Google Sheet !", state="complete")
                    st.rerun()
                except Exception as e:
                    if "429" in str(e):
                        st.error("🛑 Quota quotidien épuisé sur Google. Réessaie demain !")
                    else:
                        st.error(f"Erreur d'analyse : {e}")

    # --- 8. AFFICHAGE DES RÉSULTATS ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {target}")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("### 💰 Finances")
        st.metric("CA", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(C_DETTE, '0')} M€")
        st.write(f"**Trésorerie :** {row.get(C_CASH, '0')} M€")
    with f2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**Analyse ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")
    with f3:
        st.markdown("### 🎯 Analyse CIB")
        st.success(f"**Angle :** {row.get(C_ANGLE, 'N/A')}")
        st.write(f"**News :** {row.get(C_ACTU, 'N/A')}")