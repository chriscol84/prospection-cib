import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# 1. CONFIGURATION DE LA PAGE
st.set_page_config(page_title="CRM Prospection Christophe", layout="wide", page_icon="💼")

# 2. INITIALISATION DE L'IA (AUTO-DÉTECTION DES MODÈLES)
# Cette section scanne votre compte pour trouver le meilleur modèle disponible (2.5, 2.0 ou 1.5)
model = None
selected_model_name = "Recherche de modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if available_models:
            # On cherche par priorité de puissance
            best_model = next((m for m in available_models if "2.5" in m or "2.0" in m or "1.5" in m), available_models[0])
            model = genai.GenerativeModel(best_model)
            selected_model_name = best_model
        else:
            st.error("Aucun modèle compatible trouvé sur votre compte Google AI.")
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# 3. CONNEXION ET CHARGEMENT (LE BULLDOZER DE COLONNES)
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def load_data():
    # Lecture de l'onglet "Prospection"
    df = conn.read(worksheet="Prospection")
    # NETTOYAGE CRUCIAL : Tout en minuscules et sans espaces pour éviter les erreurs de lecture
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.fillna("")

df = load_data()

# 4. VÉRIFICATION DU NOM DE LA COLONNE CIBLE
# On cherche en minuscules suite au nettoyage
nom_col = "nom de l'entité"

if nom_col not in df.columns:
    st.error(f"❌ La colonne '{nom_col}' est introuvable.")
    st.write("Colonnes détectées (nettoyées) :", df.columns.tolist())
    st.stop()

# --- GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Christophe")
st.caption(f"🤖 Moteur actif : `{selected_model_name}` | Débit : 6 RPM max")

# Barre latérale pour la recherche
search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# AFFICHAGE DU TABLEAU (Priorité réintégrée)
cols_a_afficher = [nom_col, "priorité", "statut follow-up", "secteur", "ca (m€)"]
cols_existantes = [c for c in cols_a_afficher if c in df.columns]
st.dataframe(filtered_df[cols_existantes], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    
    # Sélection de la cible
    selected_company = st.selectbox("🎯 Travailler sur la société :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- SECTION 1 : MISE À JOUR MANUELLE (Sécurisée) ---
    st.subheader("📝 Suivi Commercial & Priorisation")
    c1, c2 = st.columns(2)
    
    with c1:
        # Statut Follow-up
        opt_s = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        v_s = str(row.get("statut follow-up", "")).strip()
        n_statut = st.selectbox("Statut actuel :", opt_s, index=opt_s.index(v_s) if v_s in opt_s else 0)
        
        # Priorité (Fix du bug de disparition et du ValueError)
        opt_p = ["P1", "P2", "P3"]
        v_p = str(row.get("priorité", "")).strip().upper()
        n_prio = st.selectbox("Priorité (P1-P3) :", opt_p, index=opt_p.index(v_p) if v_p in opt_p else 2)
        
    with c2:
        n_com = st.text_area("Notes de suivi / Commentaires :", value=str(row.get("commentaires", "")))

    if st.button("💾 Enregistrer les modifications manuelles"):
        df.at[idx, "statut follow-up"] = n_statut
        df.at[idx, "priorité"] = n_prio
        df.at[idx, "commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear() # On force la relecture pour voir le changement
        st.success("✅ Modifications sauvegardées !")
        st.rerun()

    # --- SECTION 2 : ENRICHISSEMENT IA (Respect des 6 RPM) ---
    st.divider()
    st.subheader("🤖 Intelligence Marché & Analyse IA")
    
    temps_ecoule = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.5 - temps_ecoule)

    if st.button(f"🚀 Lancer l'analyse experte pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Respect du quota : Veuillez patienter {int(attente)} secondes.")
        elif model is None:
            st.error("IA non opérationnelle.")
        else:
            with st.status("Analyse en cours...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                prompt = f"Expert CIB. Analyse {selected_company}. JSON: {{'esg': '...', 'actu': '...', 'angle': '...', 'score': 1-5}}"
                
                try:
                    response = model.generate_content(prompt)
                    # Extraction JSON robuste
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    # Enregistrement (dans les colonnes nettoyées)
                    df.at[idx, "stratégie esg"] = res.get('esg', '')
                    df.at[idx, "actualité récente"] = res.get('actu', '')
                    df.at[idx, "angle d'attaque"] = res.get('angle', '')
                    df.at[idx, "potentiel (1-5)"] = res.get('score', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Analyse terminée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")

    # --- SECTION 3 : FICHE QUALITATIVE (DONNÉES FINANCIÈRES RÉELLES) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Données Financières")
        # On appelle les colonnes en MINUSCULES car on a tout nettoyé au chargement
        st.write(f"**Chiffre d'Affaires :** {row.get('ca (m€)', 'Non trouvé')} M€")
        st.write(f"**EBITDA :** {row.get('ebitda (m€)', 'Non trouvé')} M€")
        st.write(f"**Dette Nette :** {row.get('dette nette (m€)', 'Non trouvé')} M€")
        st.write(f"**Trésorerie :** {row.get('trésorerie (m€)', 'Non trouvé')} M€")
        st.write(f"**Levier :** {row.get('levier (x)', 'N/A')} x")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('secteur', 'N/A')}")
        st.info(f"**ESG :** {row.get('stratégie esg', 'Analyse non lancée')}")
        st.error(f"**Controverses :** {row.get('controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche Commerciale")
        st.success(f"**Angle d'Attaque :** {row.get('angle d\'attaque', 'À définir')}")
        st.write(f"**Dernière News :** {row.get('actualité récente', 'N/A')}")
        st.write(f"**Priorité :** {row.get('priorité', 'P3')}")
        st.write(f"**Potentiel Score :** ⭐ {row.get('potentiel (1-5)', '0')}/5")