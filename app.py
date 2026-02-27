import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION DE L'IA (LOGIQUE DE REPLI / FALLBACK)
model = None
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        
        # On teste les noms de modèles un par un pour éviter le 404
        # On inclut le 2.5 que vous voyez dans votre console
        model_names = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-2.0-flash-exp', 'gemini-2.5-flash']
        
        for m_name in model_names:
            try:
                test_model = genai.GenerativeModel(m_name)
                # Test rapide pour voir si le modèle répond
                model = test_model
                break # Si on arrive ici, c'est que le modèle est valide
            except:
                continue
                
        if model is None:
            st.error("Aucun modèle Gemini n'a été trouvé avec votre clé.")
    except Exception as e:
        st.error(f"Erreur d'initialisation : {e}")

# 3. CONNEXION AUX DONNÉES
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    df = conn.read(worksheet="Prospection")
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()
nom_col = "Nom de l'entité"

# --- GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=11)

# --- INTERFACE ---
st.title("🚀 CRM Intelligence CIB - Christophe")

# Recherche
search = st.sidebar.text_input(f"🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

st.dataframe(filtered_df[[nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]], 
             use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Action sur :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MODIFICATION MANUELLE ---
    st.subheader("📝 Suivi & Commentaires")
    c1, c2 = st.columns(2)
    with c1:
        n_statut = st.selectbox("Statut :", ["À contacter", "Appelé", "RDV fixé", "En cours", "Client"], index=0)
        n_prio = st.selectbox("Priorité :", ["P1", "P2", "P3"], index=2)
    with c2:
        n_com = st.text_area("Notes :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Sauvegarder les notes"):
        df.at[idx, "Statut Follow-up"] = n_statut
        df.at[idx, "Priorité"] = n_prio
        df.at[idx, "Commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.success("✅ Mis à jour !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA (SÉCURITÉ 6 RPM) ---
    st.divider()
    st.subheader(f"🤖 Analyse IA ({model.model_name if model else 'N/A'})")
    
    now = datetime.now()
    attente = max(0, 11.0 - (now - st.session_state.last_request_time).total_seconds())

    if st.button(f"🚀 Lancer l'analyse pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Attendez {int(attente)}s (Quota 6 RPM)")
        elif model is None:
            st.error("Modèle IA introuvable. Vérifiez votre clé.")
        else:
            with st.spinner("Analyse en cours..."):
                st.session_state.last_request_time = datetime.now()
                prompt = f"Expert CIB. Analyse {selected_company}. Réponds en JSON: {{'esg': '...', 'actu': '...', 'angle': '...', 'score': 1-5}}"
                try:
                    response = model.generate_content(prompt)
                    # Extraction JSON robuste
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    # Mapping
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    df.at[idx, "Potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("✅ Analyse enregistrée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    # --- SECTION 3 : FICHE DE SYNTHÈSE ---
    st.divider()
    st.subheader(f"🔍 Fiche : {selected_company}")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.write(f"**CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
    with s2:
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'N/A')}")
    with s3:
        st.success(f"**Angle :** {row.get('Angle d\'Attaque', 'N/A')}")
        st.write(f"**News :** {row.get('Actualité Récente', 'N/A')}")

# --- PETIT OUTIL DE DEBUG (En bas de page) ---
with st.expander("🛠️ Debug : Liste des modèles autorisés pour votre clé"):
    if "GEMINI_API_KEY" in st.secrets:
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            st.write(available_models)
        except:
            st.write("Impossible de lister les modèles.")