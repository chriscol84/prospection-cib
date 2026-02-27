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

# --- 2. INITIALISATION DE L'IA (AUTO-DÉTECTION) ---
model = None
selected_model_name = "Recherche..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        available_models = [
            m.name for m in genai.list_models() 
            if 'generateContent' in m.supported_generation_methods
        ]
        if available_models:
            best = next((m for m in available_models if "2.5" in m or "2.0" in m or "1.5" in m), available_models[0])
            model = genai.GenerativeModel(best)
            selected_model_name = best
    except Exception as e:
        st.error(f"Erreur API Google : {e}")

# --- 3. CHARGEMENT ET NETTOYAGE (LE BULLDOZER) ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=20)
def load_data():
    # Lecture de l'onglet "Prospection"
    df = conn.read(worksheet="Prospection")
    # NETTOYAGE RADICAL : On enlève les espaces, les points, et on met tout en minuscule
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("(", "").replace(")", "") for c in df.columns]
    return df.fillna("")

df = load_data()

# Identification de la colonne Nom (nettoyée)
nom_col = "nom_de_l'entité"

if nom_col not in df.columns:
    st.error(f"❌ La colonne '{nom_col}' est introuvable.")
    with st.expander("Voir les colonnes détectées"):
        st.write(df.columns.tolist())
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("🚀 CRM Intelligence CIB - Christophe")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Statut : Prêt")

# Sidebar : Recherche et Debug
st.sidebar.header("Paramètres")
search = st.sidebar.text_input("🔍 Rechercher une société", "")
if st.sidebar.button("♻️ Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Affichage du tableau (Colonnes nettoyées)
cols_view = [nom_col, "priorité", "statut_follow-up", "secteur", "ca_m€"]
cols_ok = [c for c in cols_view if c in df.columns]
st.dataframe(filtered_df[cols_ok], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    
    selected_company = st.selectbox("🎯 Action sur :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- 6. SECTION MODIFICATION MANUELLE ---
    st.subheader("📝 Suivi & Priorisation")
    c1, c2 = st.columns(2)
    
    with c1:
        st_opts = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        v_s = str(row.get("statut_follow-up", "")).strip()
        idx_s = st_opts.index(v_s) if v_s in st_opts else 0
        n_statut = st.selectbox("Nouveau Statut :", st_opts, index=idx_s)
        
        pr_opts = ["P1", "P2", "P3"]
        v_p = str(row.get("priorité", "")).strip().upper()
        idx_p = pr_opts.index(v_p) if v_p in pr_opts else 2
        n_prio = st.selectbox("Priorité (P1-P3) :", pr_opts, index=idx_p)
        
    with c2:
        n_com = st.text_area("Notes de suivi :", value=str(row.get("commentaires", "")))

    if st.button("💾 Sauvegarder les modifications"):
        df.at[idx, "statut_follow-up"] = n_statut
        df.at[idx, "priorité"] = n_prio
        df.at[idx, "commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données sauvegardées !")
        st.rerun()

    # --- 7. ANALYSE IA (STOP INFLATION) ---
    st.divider()
    st.subheader("🤖 Intelligence Marché")
    
    diff = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.5 - diff)

    if st.button(f"🚀 Lancer l'analyse IA pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Quota 6 RPM : attendez {int(attente)}s.")
        elif model is None:
            st.error("IA non configurée.")
        else:
            with st.status("Analyse en cours...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                # On demande un format court pour éviter l'inflation
                prompt = f"Analyse flash de la société {selected_company}. Secteur: {row.get('secteur')}. Donne un JSON court avec les clés 'esg', 'actu', 'angle', 'score' (1-5). Sois synthétique (max 2 phrases par clé)."
                
                try:
                    response = model.generate_content(prompt)
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    # RÉINITIALISATION ET ÉCRITURE (Pour stopper l'inflation)
                    df.at[idx, "stratégie_esg"] = str(res.get('esg', ''))
                    df.at[idx, "actualité_récente"] = str(res.get('actu', ''))
                    df.at[idx, "angle_d'attaque"] = str(res.get('angle', ''))
                    df.at[idx, "potentiel_1-5"] = str(res.get('score', ''))
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Analyse terminée !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")

    # --- 8. FICHE QUALITATIVE (MAPPING ROBUSTE) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Finances")
        # On utilise row.get avec les noms nettoyés (espaces -> _)
        st.write(f"**CA :** {row.get('ca_m€', 'N/A')} M€")
        st.write(f"**EBITDA :** {row.get('ebitda_m€', 'N/A')} M€")
        st.write(f"**Dette Brute :** {row.get('dette_brute', 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get('trésorerie_m€', 'N/A')} M€")
        st.write(f"**Levier :** {row.get('levier_x', 'N/A')} x")

    with s2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.write(f"**Secteur :** {row.get('secteur', 'N/A')}")
        st.info(f"**ESG :** {row.get('stratégie_esg', 'Non analysé')}")
        st.error(f"**Controverses :** {row.get('controverses', 'RAS')}")

    with s3:
        st.markdown("### 🎯 Approche Commerciale")
        st.success(f"**Angle :** {row.get('angle_d\'attaque', 'À définir')}")
        st.write(f"**News :** {row.get('actualité_récente', 'N/A')}")
        st.write(f"**Priorité :** {row.get('priorité', 'P3')}")
        st.write(f"**Score :** ⭐ {row.get('potentiel_1-5', '0')}/5")