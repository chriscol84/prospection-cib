import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="CRM CIB Christophe", layout="wide", page_icon="💼")

# --- 2. INITIALISATION IA (AVEC GROUNDING GOOGLE SEARCH) ---
model = None
selected_model_name = "Détection..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On liste les modèles pour éviter l'erreur 404
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if available_models:
            # On cherche le modèle flash le plus récent
            best = next((m for m in available_models if "2.0" in m or "1.5" in m), available_models[0])
            
            # ACTIVATION DU DEEP SEARCH (google_search_retrieval)
            model = genai.GenerativeModel(
                model_name=best,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# --- 3. CHARGEMENT ET NETTOYAGE DES DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=20)
def load_data():
    df = conn.read(worksheet="Prospection")
    # On nettoie les espaces pour éviter les erreurs de mapping
    df.columns = [str(c).strip() for c in df.columns]
    return df.fillna("")

df = load_data()
nom_col = "Nom de l'entité"

if nom_col not in df.columns:
    st.error(f"❌ Colonne '{nom_col}' introuvable.")
    st.stop()

# --- 4. GESTION DU DÉBIT (ANTI-BLOCAGE 6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("🚀 Intelligence CIB : Deep Financial Search")
st.caption(f"🤖 Moteur : `{selected_model_name}` | Grounding : Web Search 2026")

search = st.sidebar.text_input("🔍 Rechercher une société", "")
mask = df[nom_col].str.contains(search, case=False, na=False)
filtered_df = df[mask]

# Tableau principal
cols_tableau = [nom_col, "Priorité", "Statut Follow-up", "Secteur", "CA (M€)"]
st.dataframe(filtered_df[[c for c in cols_tableau if c in df.columns]], use_container_width=True, hide_index=True)

if not filtered_df.empty:
    st.divider()
    selected_company = st.selectbox("🎯 Action sur :", filtered_df[nom_col].tolist())
    idx = df[df[nom_col] == selected_company].index[0]
    row = df.loc[idx]

    # --- 6. SECTION MODIFICATION MANUELLE ---
    st.subheader("📝 Suivi Commercial")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st_opts = ["À contacter", "Appelé", "RDV fixé", "En cours", "Closing", "Perdu", "Client"]
        v_s = str(row.get("Statut Follow-up", "")).strip()
        idx_s = st_opts.index(v_s) if v_s in st_opts else 0
        n_statut = st.selectbox("Statut actuel :", st_opts, index=idx_s)
        
        pr_opts = ["P1", "P2", "P3"]
        v_p = str(row.get("Priorité", "")).strip().upper()
        idx_p = pr_opts.index(v_p) if v_p in pr_opts else 2
        n_prio = st.selectbox("Priorité (P1-P3) :", pr_opts, index=idx_p)

    with col_m2:
        n_com = st.text_area("Notes de suivi :", value=str(row.get("Commentaires", "")))

    if st.button("💾 Sauvegarder les modifications"):
        df.at[idx, "Statut Follow-up"] = n_statut
        df.at[idx, "Priorité"] = n_prio
        df.at[idx, "Commentaires"] = n_com
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Données enregistrées !")
        st.rerun()

    # --- 7. ANALYSE IA (DEEP SEARCH : CHIFFRES + INFOS) ---
    st.divider()
    st.subheader("🤖 Deep Search (Recherche web en temps réel)")
    
    diff = (datetime.now() - st.session_state.last_request_time).total_seconds()
    attente = max(0, 11.5 - diff)

    if st.button(f"🚀 Lancer la recherche financière pour {selected_company}"):
        if attente > 0:
            st.warning(f"⏳ Respect du quota : attendez {int(attente)}s.")
        elif model is None:
            st.error("IA non configurée.")
        else:
            with st.status("Recherche web et analyse des rapports...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                
                # Prompt spécifique pour forcer l'extraction de chiffres via recherche web
                prompt = f"""
                Recherche les données financières 2024-2025 de la société {selected_company}. 
                Réponds EXCLUSIVEMENT en JSON avec ces clés (nombres seuls pour les finances) :
                {{
                    "ca": "Chiffre d'affaires en M€",
                    "ebitda": "EBITDA en M€",
                    "dette": "Dette Brute en M€",
                    "cash": "Trésorerie en M€",
                    "esg": "synthèse ESG courte",
                    "actu": "dernière news financière",
                    "angle": "conseil approche CIB"
                }}
                Si une donnée est introuvable, mets 0.
                """
                
                try:
                    response = model.generate_content(prompt)
                    txt = response.text
                    res = json.loads(txt[txt.find('{'):txt.rfind('}')+1])
                    
                    # Mise à jour des colonnes financières et qualitatives
                    df.at[idx, "CA (M€)"] = res.get('ca', 0)
                    df.at[idx, "EBITDA (M€)"] = res.get('ebitda', 0)
                    df.at[idx, "Dette Brute"] = res.get('dette', 0)
                    df.at[idx, "Trésorerie (M€)"] = res.get('cash', 0)
                    df.at[idx, "Stratégie ESG"] = res.get('esg', '')
                    df.at[idx, "Actualité Récente"] = res.get('actu', '')
                    df.at[idx, "Angle d'Attaque"] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données récupérées et Sheet mis à jour !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la recherche : {e}")

    # --- 8. FICHE QUALITATIVE (TABLEAU DE BORD FINAL) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {selected_company}")
    s1, s2, s3 = st.columns(3)
    
    with s1:
        st.markdown("### 💰 Finances (Live Search)")
        st.metric("Chiffre d'Affaires", f"{row.get('CA (M€)', 'N/A')} M€")
        st.metric("EBITDA", f"{row.get('EBITDA (M€)', 'N/A')} M€")
        st.write(f"**Dette Brute :** {row.get('Dette Brute', 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get('Trésorerie (M€)', 'N/A')} M€")

    with s2:
        st.markdown("### 🌍 Stratégie")
        st.info(f"**ESG :** {row.get('Stratégie ESG', 'N/A')}")
        st.write(f"**Secteur :** {row.get('Secteur', 'N/A')}")
        st.write(f"**Maison Mère :** {row.get('Maison Mère (Groupe)', 'N/A')}")

    with s3:
        st.markdown("### 🎯 Opportunité")
        st.success(f"**Angle d'Attaque :** {row.get('Angle d\'Attaque', 'À définir')}")
        st.write(f"**Dernière News :** {row.get('Actualité Récente', 'N/A')}")
        st.write(f"**Priorité :** {row.get('Priorité', 'P3')}")