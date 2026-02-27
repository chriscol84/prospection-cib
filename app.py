import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import google.generativeai as genai
import json
import time
from datetime import datetime, timedelta

# --- 1. CONFIGURATION DE L'INTERFACE ---
st.set_page_config(
    page_title="CRM Prospection Christophe", 
    layout="wide", 
    page_icon="💼"
)

# --- 2. INITIALISATION DE L'IA (DEEP SEARCH ACTIF) ---
model = None
selected_model_name = "Détection du modèle..."

if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # On cherche le meilleur modèle disponible (2.0 ou 1.5)
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        if available_models:
            best_m = next((m for m in available_models if "2.0" in m or "1.5" in m), available_models[0])
            # ACTIVATION DE LA RECHERCHE WEB GOOGLE (Grounding)
            model = genai.GenerativeModel(
                model_name=best_m,
                tools=[{"google_search_retrieval": {}}] 
            )
            selected_model_name = best_m
    except Exception as e:
        st.error(f"Erreur d'accès à l'API Google : {e}")

# --- 3. CHARGEMENT ET MAPPING DES DONNÉES ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=15)
def load_data():
    # Lecture de l'onglet "Prospection"
    data = conn.read(worksheet="Prospection")
    # Nettoyage des espaces pour éviter les erreurs de mapping
    data.columns = [str(c).strip() for c in data.columns]
    return data.fillna("")

df = load_data()

# --- MAPPING EXACT DE VOS 18 COLONNES ---
COL_NOM = "Nom (FR) (Dénomination sociale)"
COL_CA = "CA (M€) (Chiffre d'affaires)"
COL_EBITDA = "EBITDA (M€) (Rentabilité opérationnelle)"
COL_DETTE = "Dette Financière Brute (Endettement total)"
COL_CASH = "Trésorerie (M€) (Liquidités)"
COL_PRIO = "Priorité (P1-P3) (P1 = Décision Benelux + Actualité + Trade/Sponsor)"
COL_ACTU = "Dernière Actualité (Signal faible / M&A / News)"
COL_ESG = "Controverses (ESG) (Risques identifiés)"
COL_ANGLE = "Angle d'Attaque (Trade Finance, Refi, Acquisition Finance)"
COL_SECTEUR = "Secteur & Segment (Industrie)"
COL_ACCROCHE = "Accroche Personnalisée (Ice breaker ciblé)"

# Vérification du point d'entrée
if COL_NOM not in df.columns:
    st.error(f"❌ La colonne '{COL_NOM}' est introuvable.")
    with st.expander("Vérifier les titres détectés dans votre Sheet"):
        st.write(df.columns.tolist())
    st.stop()

# --- 4. GESTION DU QUOTA (6 RPM) ---
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = datetime.now() - timedelta(seconds=12)

# --- 5. INTERFACE PRINCIPALE ---
st.title("💼 CRM Prospection CIB - Christophe")
st.caption(f"🤖 IA : `{selected_model_name}` | Grounding : Recherche Web Temps Réel")

# Sidebar : Recherche et Filtres
search_query = st.sidebar.text_input("🔍 Rechercher une société (Nom)", "")
if st.sidebar.button("♻️ Actualiser la base"):
    st.cache_data.clear()
    st.rerun()

# Filtrage du DataFrame
mask = df[COL_NOM].str.contains(search_query, case=False, na=False)
filtered_df = df[mask]

# Tableau principal (Vue synthétique)
st.subheader("📋 Pipeline de Prospection")
tableau_cols = [COL_NOM, COL_PRIO, COL_CA, COL_SECTEUR]
st.dataframe(
    filtered_df[[c for c in tableau_cols if c in df.columns]], 
    use_container_width=True, 
    hide_index=True
)

if not filtered_df.empty:
    st.divider()
    
    # --- 6. FORMULAIRE D'EDITION MANUELLE ---
    target = st.selectbox("🎯 Sélectionner pour analyse ou édition :", filtered_df[COL_NOM].tolist())
    idx = df[df[COL_NOM] == target].index[0]
    row = df.loc[idx]

    st.subheader(f"📝 Gestion Commerciale : {target}")
    c1, c2 = st.columns(2)
    
    with c1:
        # Priorité
        p_list = ["P1", "P2", "P3"]
        curr_p = str(row.get(COL_PRIO, "P3")).split(" ")[0].strip().upper() # On prend juste P1, P2 ou P3
        p_idx = p_list.index(curr_p) if curr_p in p_list else 2
        new_prio = st.selectbox("Niveau de Priorité :", p_list, index=p_idx)

    with c2:
        new_note = st.text_area("Notes / Accroche Personnalisée :", value=str(row.get(COL_ACCROCHE, "")))

    if st.button("💾 Sauvegarder les notes"):
        df.at[idx, COL_PRIO] = new_prio
        df.at[idx, COL_ACCROCHE] = new_note
        conn.update(worksheet="Prospection", data=df)
        st.cache_data.clear()
        st.success("Modifications enregistrées !")
        st.rerun()

    # --- 7. DEEP SEARCH IA (GROUNDING FINANCIER) ---
    st.divider()
    st.subheader("🤖 Intelligence Deep Search (CA, EBITDA, Dette, Cash)")
    
    diff = (datetime.now() - st.session_state.last_request_time).total_seconds()
    wait = max(0, 11.5 - diff)

    if st.button(f"🚀 Lancer la recherche web financière pour {target}"):
        if wait > 0:
            st.warning(f"⏳ Quota 6 RPM : Veuillez patienter {int(wait)}s.")
        elif model is None:
            st.error("IA non configurée.")
        else:
            with st.status("Recherche web en cours (Grounding)...", expanded=True) as status:
                st.session_state.last_request_time = datetime.now()
                
                # Prompt chirurgical pour éviter l'inflation et trouver les chiffres
                prompt = f"""
                Recherche les données financières 2024-2025 de {target} (Secteur: {row.get(COL_SECTEUR)}).
                Donne UNIQUEMENT un JSON avec ces clés (valeurs numériques sans texte pour les finances) :
                {{
                    "ca": "valeur du Chiffre d'Affaires en M€",
                    "ebitda": "valeur de l'EBITDA en M€",
                    "dette": "Dette Financière Brute en M€",
                    "cash": "Trésorerie en M€",
                    "esg": "synthèse risques ESG (10 mots max)",
                    "actu": "dernière news financière majeure",
                    "angle": "angle d'attaque commercial cible"
                }}
                Si un chiffre est inconnu, mets 0.
                """
                
                try:
                    response = model.generate_content(prompt)
                    raw_txt = response.text
                    res = json.loads(raw_txt[raw_txt.find('{'):raw_txt.rfind('}')+1])
                    
                    # Mise à jour (On remplace les anciennes valeurs par les nouvelles)
                    df.at[idx, COL_CA] = res.get('ca', row.get(COL_CA))
                    df.at[idx, COL_EBITDA] = res.get('ebitda', row.get(COL_EBITDA))
                    df.at[idx, COL_DETTE] = res.get('dette', row.get(COL_DETTE))
                    df.at[idx, COL_CASH] = res.get('cash', row.get(COL_CASH))
                    df.at[idx, COL_ESG] = res.get('esg', '')
                    df.at[idx, COL_ACTU] = res.get('actu', '')
                    df.at[idx, COL_ANGLE] = res.get('angle', '')
                    
                    conn.update(worksheet="Prospection", data=df)
                    st.cache_data.clear()
                    status.update(label="✅ Données récupérées et Sheet mis à jour !", state="complete")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur d'analyse : {e}")

    # --- 8. FICHE QUALITATIVE (TABLEAU DE BORD) ---
    st.divider()
    st.subheader(f"🔍 Fiche Qualitative : {target}")
    
    f1, f2, f3 = st.columns(3)
    
    with f1:
        st.markdown("### 💰 Finances (Live Search)")
        st.metric("Chiffre d'Affaires", f"{row.get(COL_CA, 'N/A')} M€")
        st.metric("EBITDA", f"{row.get(COL_EBITDA, 'N/A')} M€")
        st.write(f"**Dette Brute :** {row.get(COL_DETTE, 'N/A')} M€")
        st.write(f"**Trésorerie :** {row.get(COL_CASH, 'N/A')} M€")

    with f2:
        st.markdown("### 🌍 Stratégie & ESG")
        st.info(f"**Risques/ESG :** {row.get(COL_ESG, 'Aucune donnée')}")
        st.write(f"**Secteur :** {row.get(COL_SECTEUR, 'N/A')}")
        st.write(f"**Maison Mère :** {row.get('Siège & Maison-mère (Localisation du décisionnaire)', 'N/A')}")

    with f3:
        st.markdown("### 🎯 Approche CIB")
        st.success(f"**Angle d'Attaque :** {row.get(COL_ANGLE, 'À définir')}")
        st.write(f"**Dernière News :** {row.get(COL_ACTU, 'N/A')}")
        st.write(f"**Priorité :** {row.get(COL_PRIO, 'P3')}")