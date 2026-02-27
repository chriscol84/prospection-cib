import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="CRM Prospection Christophe", 
    layout="wide", 
    page_icon="💼"
)

# --- 2. INITIALISATION DE L'IA AVEC RECHERCHE GOOGLE ---
model = None
selected_model_name = "Recherche de moteur..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On utilise spécifiquement 1.5 Flash ou 2.0 Flash pour la recherche web
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if available_models:
            best = next((m for m in available_models if "2.0" in m or "1.5" in m), available_models[0])
            # On active les outils de recherche Google si disponibles dans l'API
            model = genai.GenerativeModel(
                model_name=best,
                tools=[{"google_search": {}}] # Active la recherche en temps réel
            )
            selected_model_name = best
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# --- 3. CHARGEMENT ET NETTOYAGE DES DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=20)
def load_data():
    df = conn.read(worksheet="Prospection")
    # On garde les noms de colonnes originaux pour l'écriture mais on les nettoie pour la lecture
    return df.fillna("")

df = load_data()
# On définit le nom de la colonne pivot (assurez-vous qu'elle existe exactement ainsi)
nom_col = "Nom de l'entité"

if nom_col not in df.columns:
    st.error(f"❌ La colonne '{nom_col}' est introuvable.")
    st.write("Colonnes détectées :", df.columns.tolist())
    st.stop()

# --- 4. GESTION DU DÉBIT (6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("🚀 Intelligence CIB : Recherche Profonde Financière")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Mode : Google Search Grounding")

search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Tableau principal
cols_view = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
st.dataframe(filtered_df[[c for c in cols_view if c in df.columns]], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Action sur :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- 6. SECTION MODIFICATION MANUELLE ---
    st.subheader("📝 Suivi Manuel")
    c1, c2 = st.columns(2)
    with c1:
        st_opts = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        v_s = str(row.get("Statut Follow-up", "")).strip()
        idx_s = st_opts.index(v_s) if v_s in st_opts else 0
        n_statut = st.selectbox("Nouveau Statut :", st_opts, index=idx_s)
    with c2:
        n_com = st.text_area("Notes de suivi :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Sauvegarder"):
        df.at[idx, "Statut Follow-up"] = n_statut
        df.at[idx, "Commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données enregistrées !")
        st.rerun()

    # --- 7. ANALYSE IA (RECHERCHE PROFONDE) ---
    st.divider()
    st.subheader("🤖 Deep Search : Finances & ESG")
    
    diff = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.5 - diff)

    if st.button(f"🚀 Lancer la recherche web pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Quota 6 RPM : attendez {int(attente)}s.")
        else:
            with st.status("Recherche en cours sur le web financier...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                
                # Prompt spécifique pour forcer la recherche de chiffres
                prompt = f"""
                Effectue une recherche approfondie sur la société {selected_company}. 
                Trouve les chiffres les plus récents (2024 ou 2025).
                Réponds UNIQUEMENT avec ce format JSON :
                {{
                    "ca": "valeur du CA en M€ (nombre seul)",
                    "ebitda": "valeur de l'EBITDA en M€ (nombre seul)",
                    "dette": "dette brute en M€ (nombre seul)",
                    "cash": "trésorerie en M€ (nombre seul)",
                    "esg": "résumé stratégie durable",
                    "actu": "dernière news financière majeure",
                    "angle": "conseil approche CIB"
                }}
                Si un chiffre n'est pas public, mets "N/A".
                """
                
                try:
                    response = model.generate_content(prompt)
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    # Mise à jour des colonnes (Mapping exact avec votre structure)
                    df.at[idx, "CA (M€)"] = res.get('ca', '')
                    df.at[idx, "EBITDA (M€)"] = res.get('ebitda', '')
                    df.at[idx, "Dette Brute"] = res.get('dette', '')
                    df.at[idx, "Trésorerie (M€)"] = res.get('cash', '')
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Recherche terminée et enregistrée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la recherche : {e}")

    # --- 8. FICHE DE SYNTHÈSE (AFFICHAGE) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Finances (Dernières données)")
        st.metric("Chiffre d'Affaires", f"{row.get('CA (M€)', 'N/A')} M€")
        st.metric("EBITDA", f"{row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Brute :** {row.get('Dette Brute', 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get('Trésorerie (M€)', 'N/A')} M€")

    with s2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'N/A')}")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")

    with s3:
        st.markdown("### 🎯 Analyse")
        st.success(f"**Angle d'Attaque :** {row.get('Angle d\'Attaque', 'N/A')}")
        st.write(f"**Actualité :** {row.get('Actualité Récente', 'N/A')}")