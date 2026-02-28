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

# --- 2. INITIALISATION IA (BASCULE 1.5 FLASH POUR QUOTA GÉNÉREUX) ---
model = None
selected_model_name = "Gemini 1.5 Flash (Mode Quota Élevé)"

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On utilise le 1.5-flash qui offre 1500 requêtes/jour gratuites
        model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            tools=[{"google_search_retrieval": {}}] 
        )
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# --- 3. CHARGEMENT ET DÉTECTION DYNAMIQUE DES COLONNES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    data = conn.read(worksheet="Prospection")
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

def find_column(keywords):
    """Trouve la colonne même si le nom change ou contient des caractères spéciaux."""
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
    st.error("❌ Impossible d'identifier la colonne pivot 'Nom'.")
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_req_time" not in st.session_state:
    st.session_state.last_req_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("🚀 CRM CIB Intelligence - Christophe")
st.info(f"Moteur : **{selected_model_name}** | Statut : Prêt pour le Deep Search")



with st.sidebar:
    st.header("Filtrage & Debug")
    search_query = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Actualiser le Sheet"):
        st.cache_data.clear()
        st.rerun()

# Filtrage du DataFrame
mask = df[C_NOM].astype(str).str.contains(search_query, case=False, na=False)
f_df = df[mask]

# Affichage du pipeline
st.subheader("📋 Pipeline de Prospection")
st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    target = st.selectbox("🎯 Sélectionner une cible :", f_df[C_NOM].tolist())
    idx = df[df[C_NOM] == target].index[0]
    row = df.loc[idx]

    # --- 6. SECTION GESTION ---
    st.subheader(f"📝 Gestion de : {target}")
    col1, col2 = st.columns(2)
    with col1:
        p_opts = ["P1", "P2", "P3"]
        curr_p = str(row.get(C_PRIO, "P3"))[:2].upper()
        n_prio = st.selectbox("Priorité :", p_opts, index=p_opts.index(curr_p) if curr_p in p_opts else 2)
    with col2:
        n_note = st.text_area("Accroche / Notes :", value=str(row.get(C_ACC, "")))

    if st.button("💾 Sauvegarder"):
        df.at[idx, C_PRIO] = n_prio
        df.at[idx, C_ACC] = n_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données sauvegardées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (EXTRACTION WEB) ---
    st.divider()
    st.subheader("🤖 Deep Search : Extraction financière en temps réel")
    
    wait = max(0, 12.0 - (datetime.now() - st.session_state.last_req_time).total_seconds())

    if st.button(f"🚀 Lancer l'analyse web pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Quota 6 RPM : attendez {int(wait)}s.")
        elif model is None:
            st.error("L'IA est bloquée ou mal configurée.")
        else:
            with st.status("Recherche web (Grounding) en cours...", expanded=True) as status:
                st.session_state.last_req_time = datetime.now()
                
                # Prompt chirurgical pour les chiffres financiers
                prompt = f"""
                Recherche les données financières 2024 de {target}. 
                Réponds EXCLUSIVEMENT en JSON (nombres seuls pour finances) :
                {{
                    "ca": "CA en M€",
                    "ebitda": "EBITDA en M€",
                    "dette": "Dette brute en M€",
                    "cash": "Trésorerie en M€",
                    "esg": "Risques ESG (1 phrase)",
                    "actu": "News financière majeure",
                    "angle": "Conseil approche CIB"
                }}
                Si inconnu, mets 0.
                """
                
                try:
                    resp = model.generate_content(prompt)
                    res = json.loads(resp.text[resp.text.find('{'):resp.text.rfind('}')+1])
                    
                    # Mise à jour
                    df.at[idx, C_CA] = res.get('ca', row[C_CA])
                    df.at[idx, C_EBITDA] = res.get('ebitda', row[C_EBITDA])
                    df.at[idx, C_DETTE] = res.get('dette', row[C_DETTE])
                    df.at[idx, C_CASH] = res.get('cash', row[C_CASH])
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Recherche terminée et enregistrée !", state="complete")
                    st.rerun()
                except Exception as e:
                    if "429" in str(e):
                        st.error("🛑 Limite atteinte. Google a bloqué les requêtes pour aujourd'hui.")
                    else:
                        st.error(f"Erreur d'analyse : {e}")

    # --- 8. FICHE DE SYNTHÈSE QUALITATIVE ---
    st.divider()
    st.subheader(f"🔍 Résultats Intelligence Market : {target}")
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("### 💰 Finances (Live)")
        st.metric("Chiffre d'Affaires", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(C_DETTE, '0')} M€")
        st.write(f"**Trésorerie :** {row.get(C_CASH, '0')} M€")
    with f2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**Analyse ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")
    with f3:
        st.markdown("### 🎯 Opportunité")
        st.success(f"**Angle d'Attaque :** {row.get(C_ANGLE, 'N/A')}")
        st.write(f"**Dernière News :** {row.get(C_ACTU, 'N/A')}")