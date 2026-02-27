import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION IA AVEC AUTO-DÉTECTION (Anti-404)
model = None
selected_model_name = "Recherche de modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Scanner les modèles disponibles pour votre clé spécifique
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if available_models:
            # On cherche le plus récent (2.5, 2.0 ou 1.5)
            best_model = next((m for m in available_models if "2.5" in m or "2.0" in m or "1.5" in m), available_models[0])
            model = genai.GenerativeModel(best_model)
            selected_model_name = best_model
        else:
            st.error("Aucun modèle Gemini compatible trouvé sur ce compte.")
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# 3. CONNEXION GOOGLE SHEETS
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=60)
def load_data():
    # Lecture de l'onglet "Prospection"
    df = conn.read(worksheet="Prospection")
    # Nettoyage des noms de colonnes
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()

# 4. VÉRIFICATION DE LA COLONNE NOM
nom_col = "Nom de l'entité"
if nom_col not in df.columns:
    st.error(f"❌ Colonne '{nom_col}' introuvable.")
    st.write("Colonnes détectées :", df.columns.tolist())
    st.stop()

# --- GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=11)

# --- INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Christophe")
st.caption(f"🤖 Moteur actif : `{selected_model_name}` | Limite : 6 RPM")

# Sidebar : Recherche
search = st.sidebar.text_input(f"🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Affichage du tableau principal
cols_vue = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
cols_existantes = [c for c in cols_vue if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    
    selected_company = st.selectbox("🎯 Action sur la société :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MODIFICATION MANUELLE (Statut & Commentaires) ---
    st.subheader("📝 Suivi Commercial")
    col_ed1, col_ed2 = st.columns(2)
    
    with col_ed1:
        # GESTION SÉCURISÉE DU STATUT
        options_statut = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        val_statut = str(row.get("Statut Follow-up", "")).strip()
        idx_s = options_statut.index(val_statut) if val_statut in options_statut else 0
        nouveau_statut = st.selectbox("Statut Follow-up :", options_statut, index=idx_s)
        
        # GESTION SÉCURISÉE DE LA PRIORITÉ (Correction du ValueError)
        options_prio = ["P1", "P2", "P3"]
        val_prio = str(row.get("Priorité", "")).strip().upper()
        idx_p = options_prio.index(val_prio) if val_prio in options_prio else 2 # P3 par défaut
        nouveau_prio = st.selectbox("Priorité (P1-P3) :", options_prio, index=idx_p)

    with col_ed2:
        nouveau_com = st.text_area("Notes de suivi / Commentaires :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Enregistrer manuellement"):
        df.at[idx, "Statut Follow-up"] = nouveau_statut
        df.at[idx, "Priorité"] = nouveau_prio
        df.at[idx, "Commentaires"] = nouveau_com
        conn.update(worksheet="Prospection", data=df)
        st.success("✅ Données sauvegardées dans Google Sheets !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA (SÉCURITÉ 6 RPM) ---
    st.divider()
    st.subheader("🤖 Intelligence Marché")
    
    # Calcul de la pause nécessaire
    temps_ecoule = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.0 - temps_ecoule)

    if st.button(f"🚀 Lancer l'analyse IA pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Respect du quota (6 RPM) : Attendez {int(attente)}s.")
        elif model is None:
            st.error("L'IA n'est pas disponible.")
        else:
            with st.spinner(f"Analyse avec {selected_model_name}..."):
                st.session_state.last_request_time = datetime.now()
                prompt = f"Expert CIB. Analyse {selected_company}. Réponds en JSON: {{'esg': '...', 'actu': '...', 'angle': '...', 'score': 1-5}}"
                try:
                    response = model.generate_content(prompt)
                    # Extraction JSON robuste
                    raw_txt = response.text
                    res = json.loads(raw_txt[raw_txt.find('{'):raw_txt.rfind('}')+1])
                    
                    # Mise à jour des colonnes
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    df.at[idx, "Potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.success("✅ Analyse IA intégrée !")
                    st.rerun()
                except Exception as e:
                    st.error(f"Détails : {e}")

    # --- SECTION 3 : FICHE DE SYNTHÈSE VISUELLE (TABLEAU DE BORD) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown("### 💰 Finances")
        st.write(f"**CA :** {row.get('CA (M€)', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Nette :** {row.get('Dette Nette (M€)', 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get('Trésorerie (M€)', 'N/A')} M€")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'Non analysé')}")
        st.error(f"**Controverses :** {row.get('Controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche")
        st.success(f"**Angle :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"**Actualité :** {row.get('Actualité Récente', 'N/A')}")
        st.write(f"**Potentiel :** ⭐ {row.get('Potentiel (1-5)', '0')}/5")