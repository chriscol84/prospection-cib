import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION IA AVEC AUTO-DÉTECTION
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
        st.error(f"Erreur API Google : {e}")

# 3. CONNEXION ET CHARGEMENT (Gestion du cache optimisée)
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    df = conn.read(worksheet="Prospection")
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

# IMPORTANT : On charge les données
df = load_data()

# 4. SÉCURITÉ COLONNE
nom_col = "Nom de l'entité"
if nom_col not in df.columns:
    st.error(f"❌ Colonne '{nom_col}' introuvable.")
    st.stop()

# --- GESTION DU DÉBIT 6 RPM ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=11)

# --- INTERFACE ---
st.title("🚀 CRM Intelligence CIB - Christophe")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Statut : Prêt")

search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

st.dataframe(filtered_df[[nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]], 
             use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Sélectionner pour analyse :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MODIFICATION MANUELLE ---
    st.subheader("📝 Notes de suivi")
    c1, c2 = st.columns(2)
    with c1:
        options_statut = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        val_s = str(row.get("Statut Follow-up", "")).strip()
        idx_s = options_statut.index(val_s) if val_s in options_statut else 0
        nouveau_statut = st.selectbox("Statut :", options_statut, index=idx_s)
    with c2:
        nouveau_com = st.text_area("Commentaires :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Sauvegarder les notes"):
        df.at[idx, "Statut Follow-up"] = nouveau_statut
        df.at[idx, "Commentaires"] = nouveau_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear() # On vide le cache pour forcer la relecture
        st.success("✅ Notes enregistrées !")
        st.rerun()

    # --- SECTION 2 : ANALYSE IA (Correction du "moulinage") ---
    st.divider()
    st.subheader("🤖 Analyse Intelligence Marché")
    
    temps_ecoule = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.0 - temps_ecoule)

    if st.button(f"🚀 Lancer l'analyse IA pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Quota 6 RPM : Attendez {int(attente)}s.")
        elif model is None:
            st.error("IA non configurée.")
        else:
            container_ia = st.empty() # Espace pour les messages d'étape
            with container_ia.status("Analyse en cours...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                
                prompt = f"Expert CIB. Analyse {selected_company}. Réponds UNIQUEMENT en JSON: {{'esg': '...', 'actu': '...', 'angle': '...', 'score': 1-5}}"
                
                try:
                    st.write("🛰️ Interrogation de Google Gemini...")
                    response = model.generate_content(prompt)
                    
                    st.write("📥 Réception et lecture des données...")
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    st.write("📝 Écriture dans Google Sheets...")
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    df.at[idx, "Potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    
                    # C'EST ICI QUE ÇA SE JOUE :
                    st.cache_data.clear() # Forcer Streamlit à oublier l'ancienne version
                    status.update(label="✅ Analyse terminée !", state="complete", expanded=False)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de l'analyse : {e}")

    # --- SECTION 3 : AFFICHAGE DES RÉSULTATS ---
    st.divider()
    st.subheader(f"🔍 Résultats : {selected_company}")
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("**💰 Finances**")
        st.write(f"CA : {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"EBITDA : {row.get('EBITDA (M€)', 'N/A')} M€")
    with s2:
        st.markdown("**🌍 ESG & News**")
        st.info(f"ESG : {row.get('Stratégie ESG', 'N/A')}")
        st.write(f"News : {row.get('Actualité Récente', 'N/A')}")
    with s3:
        st.markdown("**🎯 Approche**")
        st.success(f"Angle : {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"Potentiel : ⭐ {row.get('Potentiel (1-5)', '0')}/5")