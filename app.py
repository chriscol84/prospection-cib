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

# --- 2. INITIALISATION IA AVEC GROUNDING (RECHERCHE WEB) ---
model = None
selected_model = "Recherche de moteur..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Détection automatique du modèle (2.0 Flash ou 1.5 Flash)
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if models:
            best_m = next((m for m in models if "2.0" in m or "1.5" in m), models[0])
            # ACTIVATION DU DEEP SEARCH (Google Search Grounding)
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model = best_m
    except Exception as e:
        st.error(f"Erreur API Google : {e}")

# --- 3. CHARGEMENT ET DÉTECTION DYNAMIQUE DES COLONNES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    data = conn.read(worksheet="Prospection")
    # On nettoie juste les espaces blancs aux extrémités des noms de colonnes
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

# FONCTION CRUCIALÈ : Trouve la colonne même si le nom change un peu
def find_column(keywords):
    for col in df.columns:
        if any(key.lower() in col.lower() for key in keywords):
            return col
    return None

# MAPPING DYNAMIQUE (Ne dépend plus d'une chaîne exacte)
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

# Sécurité : Si la colonne Nom n'est pas trouvée, on affiche un guide de secours
if not C_NOM:
    st.error("❌ Impossible d'identifier la colonne 'Nom' dans votre fichier.")
    st.write("Colonnes détectées :", df.columns.tolist())
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-429) ---
if "last_req" not in st.session_state:
    st.session_state.last_req = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE UTILISATEUR ---
st.title("🚀 CRM CIB Intelligence - Christophe")
st.caption(f"🤖 IA : `{selected_model}` | Grounding : Recherche Web 2026")

with st.sidebar:
    st.header("Filtrage & Debug")
    search = st.text_input("🔍 Rechercher une société", "")
    if st.button("♻️ Forcer l'actualisation du Sheet"):
        st.cache_data.clear()
        st.rerun()
    with st.expander("🛠️ Mapping des colonnes"):
        st.write(f"Nom : `{C_NOM}`")
        st.write(f"CA : `{C_CA}`")
        st.write(f"Priorité : `{C_PRIO}`")

# Filtrage du DataFrame
mask = df[C_NOM].astype(str).str.contains(search, case=False, na=False)
f_df = df[mask]

# Tableau de bord principal
st.subheader("📋 Pipeline de Prospection")
st.dataframe(f_df[[C_NOM, C_PRIO, C_CA, C_SECT]], use_container_width=True, hide_index=True)

if not f_df.empty:
    st.divider()
    
    # Sélection d'une société
    target = st.selectbox("🎯 Sélectionner une cible :", f_df[C_NOM].tolist())
    idx = df[df[C_NOM] == target].index[0]
    row = df.loc[idx]

    # --- 6. ÉDITION MANUELLE ---
    st.subheader(f"📝 Gestion Commerciale : {target}")
    col1, col2 = st.columns(2)
    
    with col1:
        p_opts = ["P1", "P2", "P3"]
        curr_p = str(row.get(C_PRIO, "P3"))[:2].upper()
        n_prio = st.selectbox("Priorité :", p_opts, index=p_opts.index(curr_p) if curr_p in p_opts else 2)

    with col2:
        n_note = st.text_area("Notes / Accroche :", value=str(row.get(C_ACC, "")))

    if st.button("💾 Enregistrer les notes"):
        df.at[idx, C_PRIO] = n_prio
        df.at[idx, C_ACC] = n_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données sauvegardées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (CA, EBITDA, DETTE, CASH) ---
    st.divider()
    st.subheader("🤖 Deep Search : Extraction financière en temps réel")
    
    wait = max(0, 11.5 - (datetime.now() - st.session_state.last_req).total_seconds())

    if st.button(f"🚀 Lancer l'analyse web pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Quota 6 RPM : attendez {int(wait)}s.")
        elif model is None:
            st.error("IA non disponible.")
        else:
            with st.status("Recherche web financière (Google Search)...", expanded=True) as status:
                st.session_state.last_req = datetime.now()
                
                # Prompt chirurgical pour les chiffres financiers
                prompt = f"""
                Recherche les données financières 2024-2025 de {target} (Secteur: {row.get(C_SECT)}).
                Réponds EXCLUSIVEMENT en JSON :
                {{
                    "ca": "CA en M€ (nombre)",
                    "ebitda": "EBITDA en M€ (nombre)",
                    "dette": "Dette brute en M€ (nombre)",
                    "cash": "Trésorerie en M€ (nombre)",
                    "esg": "Risques ESG (1 phrase)",
                    "actu": "News financière majeure",
                    "angle": "Conseil approche CIB"
                }}
                Si inconnu, mets 0.
                """
                
                try:
                    resp = model.generate_content(prompt)
                    res = json.loads(resp.text[resp.text.find('{'):resp.text.rfind('}')+1])
                    
                    # Injection dans le DataFrame (Écrase les valeurs vides)
                    df.at[idx, C_CA] = res.get('ca', row[C_CA])
                    df.at[idx, C_EBITDA] = res.get('ebitda', row[C_EBITDA])
                    df.at[idx, C_DETTE] = res.get('dette', row[C_DETTE])
                    df.at[idx, C_CASH] = res.get('cash', row[C_CASH])
                    df.at[idx, C_ESG] = res.get('esg', '')
                    df.at[idx, C_ACTU] = res.get('actu', '')
                    df.at[idx, C_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Recherche web terminée et enregistrée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur d'analyse : {e}")

    # --- 8. FICHE DE SYNTHÈSE QUALITATIVE ---
    st.divider()
    st.subheader(f"🔍 Résultats de l'Intelligence Market : {target}")
    
    f1, f2, f3 = st.columns(3)
    
    with f1:
        st.markdown("### 💰 Finances (Live Search)")
        st.metric("Chiffre d'Affaires", f"{row.get(C_CA, '0')} M€")
        st.metric("EBITDA", f"{row.get(C_EBITDA, '0')} M€")
        st.write(f"**Dette Brute :** {row.get(C_DETTE, '0')} M€")
        st.write(f"**Trésorerie :** {row.get(C_CASH, '0')} M€")
        if float(str(row.get(C_EBITDA, 0)).replace(',','.')) != 0:
            levier = float(str(row.get(C_DETTE, 0)).replace(',','.')) / float(str(row.get(C_EBITDA, 1)).replace(',','.'))
            st.write(f"**Levier estimé :** {levier:.2f}x")

    with f2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.info(f"**Analyse ESG :** {row.get(C_ESG, 'N/A')}")
        st.write(f"**Secteur :** {row.get(C_SECT, 'N/A')}")

    with f3:
        st.markdown("### 🎯 Analyse Opportunité")
        st.success(f"**Angle d'Attaque :** {row.get(C_ANGLE, 'À définir')}")
        st.write(f"**Dernière News :** {row.get(C_ACTU, 'N/A')}")
        st.write(f"**Priorité :** {row.get(C_PRIO, 'P3')}")